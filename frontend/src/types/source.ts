export interface SourceBlock {
  id: string;
  kind: 'heading' | 'paragraph' | 'table' | 'text' | 'markdown';
  text: string;
  page: number | null;
}

export interface SourceRange {
  block_id: string;
  start: number;
  end: number;
}

export interface ChunkSource {
  chunk_id: string;
  file_id: string;
  file_name: string;
  file_type: string;
  generation: number;
  source_type: string;
  content: string;
  page: number | null;
  time_start: number | null;
  time_end: number | null;
  media_path: string | null;
  blocks: SourceBlock[];
  locations: Record<string, SourceRange[]>;
  contents: Record<string, string>;
  original_url: string;
}
