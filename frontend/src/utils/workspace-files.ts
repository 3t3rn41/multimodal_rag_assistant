export const WORKSPACE_FILE_ACCEPT='.pdf,.docx,.txt,.md';
export const MAX_WORKSPACE_BYTES=100*1024*1024;
export function uploadProblem(file:File):string|null{
 const extension=file.name.toLowerCase().split('.').pop();
 if(!extension||!['pdf','docx','txt','md'].includes(extension))return '支持 PDF、DOCX、TXT 和 MD 文件。';
 if(file.size>MAX_WORKSPACE_BYTES)return '单个文件不能超过 100 MB。';
 if(file.size===0)return '文件为空，请选择有内容的文件。';
 return null;
}
export function acceptedUploads(files:File[]):{accepted:File[];rejected:string[]}{
 const accepted:File[]=[],rejected:string[]=[];
 for(const file of files){const problem=uploadProblem(file);if(problem)rejected.push(file.name+'：'+problem);else accepted.push(file)}
 return {accepted,rejected};
}
