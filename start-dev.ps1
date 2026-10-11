#requires -Version 5.1
<#
Start mmrag infrastructure, FastAPI, Vite, and the document worker.
Run from the project directory: .\start-dev.ps1
Python packages are never installed by this script.
-CheckOnly validates prerequisites and configuration without starting services.
-Restart stops verified project API/Worker processes before applying migrations.
-StopOnly stops verified API/Worker processes without loading project dependencies.
-StopApps also stops the verified Vite process before switching to full Compose.
#>
[CmdletBinding()]
param(
    [switch]$CheckOnly,
    [switch]$Restart,
    [switch]$StopOnly,
    [switch]$StopApps,
    [string]$CondaEnvironment = "rag",
    [string]$CondaPrefix = ""
)

$ErrorActionPreference = "Stop"
$Root = $PSScriptRoot
$Runtime = Join-Path $Root ".runtime"
$StateFile = Join-Path $Runtime "processes.json"
$ComposeFile = Join-Path $Root "compose.yaml"
$EnvFile = Join-Path $Root ".env"
$PythonExe = $null
$Records = @{}
$StartedNames = @()
$SavedEnvironment = @{}
$Signatures = @{
    backend = "backend.api.main:app"
    frontend = "vite\bin\vite.js"
    worker = "backend.task.celery_app:celery_app"
}
$LaunchMutex = $null
$MutexHeld = $false
$LocationPushed = $false
$ScriptExitCode = 1

function Invoke-Native {
    param([string]$Executable, [string[]]$Arguments, [switch]$Capture)
    $previousAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        # Native tools use stderr for progress on Windows PowerShell 5.1.
        if ($Capture) {
            $lines = @(& $Executable @Arguments 2>&1 | ForEach-Object { $_.ToString() })
        } else {
            & $Executable @Arguments 2>&1 | ForEach-Object { Write-Host $_.ToString() }
        }
        $nativeExitCode = $LASTEXITCODE
    } finally {
        $ErrorActionPreference = $previousAction
    }
    if ($nativeExitCode -ne 0) {
        if ($Capture) { $lines | ForEach-Object { Write-Host $_ } }
        throw ("{0} failed (exit {1})." -f [IO.Path]::GetFileName($Executable), $nativeExitCode)
    }
    if ($Capture) { return ($lines -join "`n") }
}

function Read-CommandJson {
    param([string]$Executable, [string[]]$Arguments)
    $content = Invoke-Native -Executable $Executable -Arguments $Arguments -Capture
    try { return ($content | ConvertFrom-Json) }
    catch { throw "Could not read the command's JSON response. Check dependencies and configuration." }
}

function Set-TemporaryEnvironment {
    param([string]$Name, [string]$Value)
    if (-not $SavedEnvironment.ContainsKey($Name)) {
        $SavedEnvironment[$Name] = [Environment]::GetEnvironmentVariable($Name, "Process")
    }
    [Environment]::SetEnvironmentVariable($Name, $Value, "Process")
}

function Find-CondaPrefix {
    if ($CondaPrefix) { return (Resolve-Path -LiteralPath $CondaPrefix).Path }
    if ($env:CONDA_DEFAULT_ENV -eq $CondaEnvironment -and $env:CONDA_PREFIX) {
        return $env:CONDA_PREFIX
    }
    $prefixes = @()
    $registryFile = Join-Path $env:USERPROFILE ".conda\environments.txt"
    if (Test-Path -LiteralPath $registryFile) {
        $prefixes = @(Get-Content -LiteralPath $registryFile | Where-Object {
            (Split-Path -Leaf $_.Trim()) -eq $CondaEnvironment -and (Test-Path -LiteralPath (Join-Path $_.Trim() "python.exe"))
        } | ForEach-Object { $_.Trim() } | Select-Object -Unique)
    }
    if (-not $prefixes.Count) {
        $condaCommand = Get-Command conda.exe -ErrorAction SilentlyContinue
        $condaProgram = if ($env:CONDA_EXE) { $env:CONDA_EXE } elseif ($condaCommand) { $condaCommand.Source } else { $null }
        if ($condaProgram) {
            $environments = Read-CommandJson $condaProgram @("env", "list", "--json")
            $prefixes = @($environments.envs | Where-Object { (Split-Path -Leaf $_) -eq $CondaEnvironment })
        }
    }
    if ($prefixes.Count -gt 1) { throw "Multiple Conda environments match $CondaEnvironment. Select one with -CondaPrefix." }
    if (-not $prefixes.Count) { throw "Conda environment $CondaEnvironment was not found. Activate it first, or pass -CondaPrefix with its directory." }
    return $prefixes[0]
}

function Save-State {
    $Records | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath $StateFile -Encoding UTF8
}

function Read-ProcessRecords {
    if (-not (Test-Path -LiteralPath $StateFile)) { return }
    try {
        $stored = Get-Content -LiteralPath $StateFile -Raw | ConvertFrom-Json
        foreach ($property in $stored.PSObject.Properties) { $Records[$property.Name] = $property.Value }
    } catch { Write-Warning "Ignoring an unreadable process record; occupied ports will still be checked." }
}

function Acquire-LaunchMutex {
    $hasher = [Security.Cryptography.SHA256]::Create()
    try { $lockHash = [BitConverter]::ToString($hasher.ComputeHash([Text.Encoding]::UTF8.GetBytes($Root.ToUpperInvariant()))).Replace("-", "").Substring(0, 16) }
    finally { $hasher.Dispose() }
    $script:LaunchMutex = New-Object Threading.Mutex($false, "Local\mmrag-start-$lockHash")
    try { $script:MutexHeld = $LaunchMutex.WaitOne(0) } catch [Threading.AbandonedMutexException] { $script:MutexHeld = $true }
    if (-not $MutexHeld) { throw "Another launcher is already running for this project." }
}

function Get-ManagedProcess {
    param([string]$Name)
    $record = $Records[$Name]
    if (-not $record -or $record.root -ne $Root) { return $null }
    $process = Get-Process -Id $record.processId -ErrorAction SilentlyContinue
    if (-not $process) { return $null }
    try {
        if ($process.StartTime.ToUniversalTime().Ticks -ne [long]$record.startTicks) { return $null }
        $info = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f $process.Id)
        $rootPattern = [regex]::Escape($Root) + '(?=[\\" \t]|$)'
        if (-not $info.CommandLine -or $info.CommandLine -notmatch $rootPattern -or
            $info.CommandLine.IndexOf($Signatures[$Name], [StringComparison]::OrdinalIgnoreCase) -lt 0) {
            return $null
        }
    } catch { return $null }
    return $process
}

function Get-ProcessTreeIds {
    param([int]$ProcessId)
    $tree = @($ProcessId)
    for ($index = 0; $index -lt $tree.Count -and $index -lt 64; $index++) {
        $children = @(Get-CimInstance Win32_Process -Filter ("ParentProcessId={0}" -f $tree[$index]))
        foreach ($child in $children) {
            if ($tree -notcontains [int]$child.ProcessId) { $tree += [int]$child.ProcessId }
        }
    }
    return $tree
}

function Stop-ManagedProcess {
    param([string]$Name)
    $process = Get-ManagedProcess $Name
    if ($process) {
        $tree = @(Get-ProcessTreeIds $process.Id)
        [array]::Reverse($tree)
        foreach ($childId in $tree) {
            $stoppingProcess = Get-Process -Id $childId -ErrorAction SilentlyContinue
            if ($stoppingProcess) {
                Stop-Process -InputObject $stoppingProcess -Force
                if (-not $stoppingProcess.WaitForExit(5000)) {
                    throw "The managed $Name process did not stop within five seconds."
                }
            }
        }
    }
    $Records.Remove($Name)
}

function Stop-ProjectProcessing {
    foreach ($name in @("backend", "worker")) { Stop-ManagedProcess $name }
}

function Stop-ProjectApplications {
    Stop-ProjectProcessing
    Stop-ManagedProcess "frontend"
}

function Assert-LocalApplicationMode {
    $services = Invoke-Native $DockerExe ($ComposeArgs + @("ps", "--services", "--status", "running")) -Capture
    foreach ($service in ($services -split "\r?\n")) {
        if ($service.Trim() -in @("backend", "frontend", "worker", "bootstrap")) {
            throw "Application containers are running. Run docker compose stop frontend backend worker bootstrap before starting local development."
        }
    }
}

function Start-ProjectInfrastructure {
    Invoke-Native $DockerExe ($ComposeArgs + @("up", "-d", "--wait", "--wait-timeout", "300", "mysql57", "redis", "minio", "qdrant"))
}

function Assert-ApplicationPort {
    param([int]$Port, [string]$Name)
    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    if (-not $connections.Count) { return }
    $process = Get-ManagedProcess $Name
    $allowed = if ($process) { @(Get-ProcessTreeIds $process.Id) } else { @() }
    foreach ($connection in $connections) {
        if ($allowed -notcontains [int]$connection.OwningProcess) {
            throw ("Port {0} is occupied by another process ({1}). Free the configured port and retry." -f $Port, $connection.OwningProcess)
        }
    }
}

function Quote-ProcessArgument {
    param([string]$Value)
    # CreateProcess takes one command line; escape quotes and trailing backslashes.
    $escaped = [regex]::Replace($Value, '(\\*)"', '$1$1\"')
    $escaped = [regex]::Replace($escaped, '(\\+)$', '$1$1')
    return '"' + $escaped + '"'
}

function Start-ManagedApp {
    param([string]$Name, [string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory)
    $process = Get-ManagedProcess $Name
    if ($process) {
        Write-Host ("    {0} is already running (PID {1})." -f $Name, $process.Id)
        return
    }
    $commandLine = ($Arguments | ForEach-Object { Quote-ProcessArgument $_ }) -join " "
    $process = Start-Process -FilePath $Executable -ArgumentList $commandLine `
        -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru `
        -RedirectStandardOutput (Join-Path $Runtime "$Name.log") `
        -RedirectStandardError (Join-Path $Runtime "$Name.err.log")
    $Records[$Name] = @{
        processId = $process.Id
        startTicks = $process.StartTime.ToUniversalTime().Ticks
        root = $Root
        fingerprint = $Config.fingerprint
    }
    $script:StartedNames += $Name
    Save-State
    Write-Host ("    Started {0} (PID {1})." -f $Name, $process.Id)
}

function Wait-Http {
    param([string]$Url, [string]$Name, [scriptblock]$Condition, [hashtable]$Headers = @{})
    $deadline = (Get-Date).AddSeconds(60)
    do {
        if ($Name -in @("backend", "frontend", "worker") -and -not (Get-ManagedProcess $Name)) {
            throw "$Name exited before becoming ready. See $Runtime\$Name.err.log."
        }
        try {
            if ($Condition) {
                $response = Invoke-RestMethod -Uri $Url -Headers $Headers -TimeoutSec 5
                if (& $Condition $response) { return }
            } else {
                $response = Invoke-WebRequest -Uri $Url -Headers $Headers -UseBasicParsing -TimeoutSec 5
                if ($response.StatusCode -eq 200) { return }
            }
        } catch {}
        Start-Sleep -Seconds 2
    } while ((Get-Date) -lt $deadline)
    throw "$Name did not become ready within 60 seconds. Check its logs and .env."
}

function Test-DockerEngine {
    $previousAction = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try {
        & $DockerExe info --format '{{.ServerVersion}}' 2>$null | Out-Null
        return $LASTEXITCODE -eq 0
    } catch { return $false }
    finally { $ErrorActionPreference = $previousAction }
}

function Assert-InfrastructurePorts {
    $ownedPorts = @()
    $containerIds = Invoke-Native $DockerExe @("ps", "--filter", "label=com.docker.compose.project=mmrag", "--format", "{{.ID}}") -Capture
    foreach ($containerId in ($containerIds -split "\r?\n" | Where-Object { $_ })) {
        $bindings = Read-CommandJson $DockerExe @("inspect", "--format", "{{json .NetworkSettings.Ports}}", $containerId)
        if ($bindings) {
            foreach ($property in $bindings.PSObject.Properties) {
                foreach ($binding in $property.Value) { $ownedPorts += [int]$binding.HostPort }
            }
        }
    }
    foreach ($port in $Config.infrastructure_ports) {
        if ((Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue) -and $ownedPorts -notcontains $port) {
            throw "Infrastructure port $port is occupied outside the mmrag container group. Free it and retry."
        }
    }
}

try {
    Push-Location $Root
    $LocationPushed = $true
    if ($StopOnly -or $StopApps) {
        if ($CheckOnly -or $Restart -or ($StopOnly -and $StopApps)) { throw "-StopOnly and -StopApps are mutually exclusive and cannot be combined with -CheckOnly or -Restart." }
        Acquire-LaunchMutex
        Read-ProcessRecords
        if ($StopApps) { Stop-ProjectApplications } else { Stop-ProjectProcessing }
        if (Test-Path -LiteralPath $Runtime) { Save-State }
        if ($StopApps) { Write-Host "Verified project API/Worker/Vite processes stopped. Infrastructure remains available." }
        else { Write-Host "Verified project API/Worker processes stopped. Infrastructure and frontend remain available." }
        $ScriptExitCode = 0
    } else {
    if (-not (Test-Path -LiteralPath $EnvFile)) { throw "Fill in .env.example and create the project .env first." }
    foreach ($commandName in @("docker.exe", "node.exe", "npm.cmd")) {
        if (-not (Get-Command $commandName -ErrorAction SilentlyContinue)) { throw "Required command not found: $commandName" }
    }
    $DockerExe = (Get-Command docker.exe).Source
    $NodeExe = (Get-Command node.exe).Source
    $NpmExe = (Get-Command npm.cmd).Source

    Write-Host "[1/5] Checking local environment and Python dependencies..."
    $resolvedPrefix = Find-CondaPrefix
    $PythonExe = Join-Path $resolvedPrefix "python.exe"
    if (-not (Test-Path -LiteralPath $PythonExe) -or -not (Test-Path -LiteralPath (Join-Path $resolvedPrefix "conda-meta"))) {
        throw "The selected directory is not a Conda Python environment: $resolvedPrefix"
    }
    Write-Host "    Python environment: $resolvedPrefix"
    $condaPaths = @("", "Library\mingw-w64\bin", "Library\usr\bin", "Library\bin", "Scripts", "bin") | ForEach-Object {
        if ($_ -eq "") { $resolvedPrefix } else { Join-Path $resolvedPrefix $_ }
    } | Where-Object { Test-Path -LiteralPath $_ }
    Set-TemporaryEnvironment "PATH" (($condaPaths -join ";") + ";" + $env:PATH)
    Set-TemporaryEnvironment "CONDA_PREFIX" $resolvedPrefix
    Set-TemporaryEnvironment "CONDA_DEFAULT_ENV" $CondaEnvironment
    Invoke-Native $PythonExe @("-c", "import sys; assert sys.version_info >= (3, 11), 'Python 3.11 or later is required in the Conda environment'")
    $dependencies = Read-CommandJson $PythonExe @("-m", "scripts.dev_setup", "check")
    if ($dependencies.missing.Count) {
        Write-Host "    Missing or incompatible Python packages:" -ForegroundColor Yellow
        $dependencies.missing | ForEach-Object { Write-Host "      $_" }
        Write-Host "    Run this command yourself, then run .\start-dev.ps1 again:" -ForegroundColor Yellow
        Write-Host ('      conda activate "{0}"' -f $resolvedPrefix)
        Write-Host '      python -m pip install -e ".[app]"'
        throw "Python dependencies need manual installation. No pip download was performed."
    }
    $Config = Read-CommandJson $PythonExe @("-m", "scripts.dev_setup", "config")
    foreach ($property in $Config.environment.PSObject.Properties) {
        Set-TemporaryEnvironment $property.Name ([string]$property.Value)
    }
    $nodeVersion = (Invoke-Native $NodeExe @("--version") -Capture).TrimStart("v").Split(".")
    $nodeMajor = [int]$nodeVersion[0]
    $nodeMinor = [int]$nodeVersion[1]
    if (-not (($nodeMajor -eq 20 -and $nodeMinor -ge 19) -or $nodeMajor -gt 22 -or ($nodeMajor -eq 22 -and $nodeMinor -ge 12))) {
        throw "Vite requires Node.js 20.19+ or 22.12+."
    }
    $FrontendRoot = Join-Path $Root "frontend"
    $ViteEntry = Join-Path $FrontendRoot "node_modules\vite\bin\vite.js"
    if (-not (Test-Path -LiteralPath $ViteEntry)) {
        if ($CheckOnly) { throw "Frontend dependencies are missing. Run npm.cmd ci in frontend." }
        Push-Location $FrontendRoot
        try { Invoke-Native $NpmExe @("ci") } finally { Pop-Location }
    }
    $ComposeArgs = @("compose", "--project-name", "mmrag", "--env-file", $EnvFile, "-f", $ComposeFile)
    Invoke-Native $DockerExe ($ComposeArgs + @("config", "--quiet"))
    if ($CheckOnly) {
        Write-Host "Prerequisites and .env configuration passed. No services were started."
        $ScriptExitCode = 0
    } else {
        Acquire-LaunchMutex
        New-Item -ItemType Directory -Path $Runtime -Force | Out-Null
        Read-ProcessRecords
        if (Test-DockerEngine) { Assert-LocalApplicationMode }
        foreach ($name in @("backend", "frontend", "worker")) {
            $process = Get-ManagedProcess $name
            if (-not $process) { $Records.Remove($name) }
            elseif ($Records[$name].fingerprint -ne $Config.fingerprint) {
                Write-Host "    Configuration changed; restarting $name."
                Stop-ManagedProcess $name
            }
        }
        if ($Restart) {
            Write-Host "    Restart requested; stopping managed API/Worker before migrations."
            Stop-ProjectProcessing
        }
        Save-State
        Assert-ApplicationPort $Config.backend_port "backend"
        Assert-ApplicationPort $Config.frontend_port "frontend"

        Write-Host "[2/5] Starting the mmrag container group..."
        if (-not (Test-DockerEngine)) {
            $desktopExe = Join-Path $env:ProgramFiles "Docker\Docker\Docker Desktop.exe"
            if (-not (Test-Path -LiteralPath $desktopExe)) { throw "Docker Desktop was not found. Start Docker manually and retry." }
            Start-Process -FilePath $desktopExe -WindowStyle Hidden
            $dockerDeadline = (Get-Date).AddMinutes(5)
            do {
                Start-Sleep -Seconds 5
                $dockerReady = Test-DockerEngine
            } while (-not $dockerReady -and (Get-Date) -lt $dockerDeadline)
            if (-not $dockerReady) { throw "Docker Desktop did not become ready within five minutes." }
        }
        Assert-InfrastructurePorts
        Assert-LocalApplicationMode
        Start-ProjectInfrastructure
        $qdrantHeaders = @{}
        if ($env:RAG_QDRANT_API_KEY) { $qdrantHeaders["api-key"] = $env:RAG_QDRANT_API_KEY }
        Wait-Http ($env:RAG_QDRANT_URL.TrimEnd("/") + "/readyz") "qdrant" -Headers $qdrantHeaders
        Invoke-Native $PythonExe @("-m", "scripts.dev_setup", "bootstrap")

        Write-Host "[3/5] Starting FastAPI..."
        Start-ManagedApp "backend" $PythonExe @("-m", "uvicorn", "backend.api.main:app", "--app-dir", $Root, "--host", $Config.backend_host, "--port", [string]$Config.backend_port) $Root
        Wait-Http ($Config.backend_url + "/health") "backend" -Condition { param($response) $response.status -eq "ok" }
        Wait-Http ($Config.backend_url + "/ready") "backend" -Condition { param($response) $response.status -eq "ready" }

        Write-Host "[4/5] Starting the document worker..."
        Start-ManagedApp "worker" $PythonExe @("-m", "celery", "--workdir", $Root, "-A", "backend.task.celery_app:celery_app", "worker", "--pool=solo", "--concurrency=1", "--loglevel=INFO", "--hostname", $Config.worker_node) $Root
        Wait-Http ($Config.backend_url + "/api/system/worker") "worker" -Condition { param($response) $response.online -eq $true }

        Write-Host "[5/5] Starting Vite and checking the API proxy..."
        Start-ManagedApp "frontend" $NodeExe @($ViteEntry) $FrontendRoot
        Wait-Http ($Config.frontend_url + "/") "frontend"
        Wait-Http ($Config.frontend_url + "/api/system/worker") "frontend" -Condition { param($response) $response.online -eq $true }
        Save-State
        Write-Host ""
        Write-Host "mmrag is ready." -ForegroundColor Green
        Write-Host ("Frontend: {0}/" -f $Config.frontend_url)
        Write-Host ("API docs: {0}/docs" -f $Config.backend_url)
        Write-Host "Logs: $Runtime"
        Write-Host "Configure the answer model in project .env; the model status page is read-only."
        $ScriptExitCode = 0
    }
    }
} catch {
    Write-Host ("Startup failed: {0}" -f $_.Exception.Message) -ForegroundColor Red
    if ($MutexHeld) {
        foreach ($name in $StartedNames) { Stop-ManagedProcess $name }
        Save-State
        Write-Host "Logs: $Runtime"
    }
} finally {
    foreach ($name in $SavedEnvironment.Keys) {
        [Environment]::SetEnvironmentVariable($name, $SavedEnvironment[$name], "Process")
    }
    if ($MutexHeld) { $LaunchMutex.ReleaseMutex() }
    if ($LaunchMutex) { $LaunchMutex.Dispose() }
    if ($LocationPushed) { Pop-Location }
}
exit $ScriptExitCode
