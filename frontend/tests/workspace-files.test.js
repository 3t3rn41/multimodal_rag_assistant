import {describe, expect, it} from 'vitest';
import {acceptedUploads, MAX_WORKSPACE_BYTES, uploadProblem, WORKSPACE_FILE_ACCEPT} from '../src/utils/workspace-files';

describe('workspace Markdown uploads', () => {
 it.each(['note.md', 'NOTE.MD'])('accepts %s with an empty browser MIME type', name => {
  expect(uploadProblem(new File(['# 中文'], name, {type: ''}))).toBeNull();
  expect(WORKSPACE_FILE_ACCEPT.split(',')).toContain('.md');
 });
 it('checks empty, oversized and unsupported files before upload', () => {
  expect(uploadProblem(new File([], 'empty.md'))).toContain('为空');
  const large = new File(['# text'], 'large.md');
  Object.defineProperty(large, 'size', {value: MAX_WORKSPACE_BYTES + 1});
  expect(uploadProblem(large)).toContain('100 MB');
  expect(uploadProblem(new File(['text'], 'wrong.html'))).toContain('MD');
 });
 it('keeps valid Markdown among mixed drag-and-drop files', () => {
  const valid = new File(['# 文档'], 'valid.md');
  const result = acceptedUploads([valid, new File(['text'], 'invalid.exe')]);
  expect(result.accepted).toEqual([valid]);
  expect(result.rejected).toHaveLength(1);
 });
});
