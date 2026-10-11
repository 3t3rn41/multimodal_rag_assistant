"""Local container probes; never invoke model providers or expose credentials."""

import argparse
import socket
from urllib.request import urlopen


def api_ready() -> bool:
    with urlopen("http://127.0.0.1:8001/ready", timeout=5) as response:
        return response.status == 200


def worker_ready() -> bool:
    from backend.task.celery_app import QUEUE_PREFIX, celery_app

    node = f"{QUEUE_PREFIX}@{socket.gethostname()}"
    replies = celery_app.control.inspect(destination=[node], timeout=3).ping() or {}
    return replies.get(node, {}).get("ok") == "pong"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("service", choices=("api", "worker"))
    service = parser.parse_args().service
    try:
        ready = api_ready() if service == "api" else worker_ready()
        return 0 if ready else 1
    except Exception:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
