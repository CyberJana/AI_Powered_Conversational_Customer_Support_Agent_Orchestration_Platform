export interface ChatSource {
  document_id: string;
  chunk_id: string;
  snippet: string;
  score: number;
}

export interface ChatRequestPayload {
  conversation_id: string | null;
  message: string;
  knowledge_base_id?: string | null;
}

export interface ChatResponsePayload {
  message_id: string;
  conversation_id: string;
  answer: string;
  confidence: number | null;
  sources: ChatSource[];
  intent: string | null;
  escalated: boolean;
}

export interface ChatMessage {
  id: string;
  sender: "customer" | "assistant" | "agent";
  content: string;
}
