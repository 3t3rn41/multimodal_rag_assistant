import { useAuthStore } from '../stores/auth';
import { useChatStore } from '../stores/chat';
import { useKbStore } from '../stores/kb';
import { useModelsStore } from '../stores/models';
import type { AuthStore, ChatStore, KbStore, ModelsStore } from '../types/workbench';
// Identity adapters only. All original requests and account cleanup remain in Pinia.
export const useWorkbenchAuth = () => useAuthStore() as unknown as AuthStore;
export const useWorkbenchChat = () => useChatStore() as unknown as ChatStore;
export const useWorkbenchKb = () => useKbStore() as unknown as KbStore;
export const useWorkbenchModels = () => useModelsStore() as unknown as ModelsStore;
