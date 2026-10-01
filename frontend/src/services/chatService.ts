import { apiClient } from "./apiClient";
import type { ChatRequestPayload, ChatResponsePayload } from "@/types/chat";

export const chatService = {
  sendMessage: async (payload: ChatRequestPayload) => {
    const { data } = await apiClient.post<ChatResponsePayload>("/chat", payload);
    return data;
  },
};
