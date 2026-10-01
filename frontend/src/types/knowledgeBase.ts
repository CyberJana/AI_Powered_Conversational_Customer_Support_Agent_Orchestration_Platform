export type DocumentStatus = "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";

export interface KnowledgeBase {
  id: string;
  organization_id: string;
  name: string;
  description: string;
  created_at: string;
}

export interface KnowledgeBaseDocument {
  id: string;
  knowledge_base_id: string;
  filename: string;
  file_type: string;
  status: DocumentStatus;
  error_message: string | null;
  created_at: string;
}
