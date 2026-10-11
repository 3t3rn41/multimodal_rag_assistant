// Types for the presentation adapter; original requests and stores remain unchanged.
type Id = number;
export interface StageMetric {status?:string;started_at?:string;completed_at?:string|null;active_since?:string|null;elapsed_ms?:number;completed?:number|null;total?:number|null}
interface IndexingReport {total:number;skipped:number;embedded:number;upserted:number}
export interface KnowledgeBase {id: Id; name: string; description?: string | null; topic_tags?: string[]; created_at?: string; enabled?: boolean}
export interface DocumentMeta {task_id?:string;task_status?: string; task_stage?: string; task_progress?: number; task_error?: string; error?: string; pipeline_state?: string; chunk_count?: number; file_size?: number; size?: number; uploaded_at?: string; created_at?: string;failed_stage?:string|null;retry_count?:number;stage_metrics?:Record<string,StageMetric>|null;indexing_report?:IndexingReport|null;task_started_at?:string|null;task_completed_at?:string|null; [key: string]: unknown}
export interface KbDocument {file_id: Id; file_name: string; file_type: string; status: string; enabled: boolean; meta?: DocumentMeta | null; upload_time?: string; file_size?: number}
export interface Citation {chunk_id: string | number; doc_id?: Id; doc_title?: string; file_name?: string | null; page?: number | null; preview?: string; source_type?: string; time_start?: number | null; time_end?: number | null; media_path?: string | null; label?: string}
export interface ChatSession {id: Id; title?: string | null; kb_ids?: Id[]; created_time?: string; mode?: string; status?: string}
interface ChatItem {type: string; content?: string; citations?: Citation[]; streaming?: boolean; messageId?: Id; feedback?: string | null; _key?: string | number; [key: string]: unknown}
export interface ChatStore {
 sessions: ChatSession[]; currentSessionId: Id | null; currentSession: ChatSession | null;
 kbs: KnowledgeBase[]; selectedKbId: Id | null;
 items: ChatItem[]; streaming: boolean; loadingSessions: boolean; loadingMessages: boolean; canAsk: boolean;
 turnSeq: number; error: string | null; notice: {type: string; text: string} | null;
 loadKbs(): Promise<void>; loadSessions(): Promise<ChatSession[]>; newSession(): Promise<void>;
 selectSession(id: Id): Promise<void>; renameSession(id: Id,title: string): Promise<void>;
 deleteSession(id: Id): Promise<void>; exportSession(id: Id): Promise<string | {markdown?: string}>;
 ask(question: string,sessionId?: Id | null): Promise<boolean>; abort(): Promise<void>;
 retryLast(): Promise<void>; regenerate(): Promise<void>;
 setFeedback(id: Id | undefined,kind: 'up' | 'down' | null): Promise<{ok: boolean; error?: string}>;
 setNotice(notice: {type: string; text: string}): void; clearNotice(): void;
}
export interface KbStore {
 kbs: KnowledgeBase[]; currentKbId: Id | null; currentKb: KnowledgeBase | null; docs: KbDocument[];
 hasParsingDocs: boolean; loading: boolean; error: string | null; errorStatus: number | null; loadKbs(): Promise<KnowledgeBase[]>; selectKb(id: Id): Promise<void>;
 loadDocs(): Promise<void>; createKb(name: string,description?: string,tags?: string[]): Promise<KnowledgeBase>;
 updateKb(id: Id,patch: Partial<KnowledgeBase>): Promise<KnowledgeBase>; deleteKb(id: Id): Promise<void>;
 uploadFiles(files: File[],progress?: (name: string,ratio: number)=>void): Promise<unknown[]>;
 uploadUrl(url: string): Promise<unknown>; reparse(id: Id): Promise<void>; removeDoc(kbId: Id,id: Id): Promise<void>;
 setDocEnabled(id: Id,enabled: boolean): Promise<void>; reportCorrection(id: Id): Promise<void>; stopPolling(): void;
}
interface ModelConfig {
 llm_base_url: string; llm_model: string;
 llm_key_configured: boolean; configured: boolean;
 readonly: boolean; configuration_source: 'environment';
 missing?: string[];
 system_models?: {configured: boolean; configuration_source: string; embedding_model: string; embedding_dimensions: number; rerank_model: string; vector_collection: string; missing: string[]; remote_services_verified: boolean};
}
export interface ModelsStore {config: ModelConfig | null; loading: boolean; configured: boolean; load(): Promise<ModelConfig>}
export interface AuthStore {
 user: {id?: Id; email: string} | null;
 loaded: boolean; error: string | null; init(): Promise<void>; login(email: string,password: string): Promise<unknown>;
 logout(): Promise<void>; clearAccount(): void;
}
export interface UploadFailure {failedFiles?: File[]}
