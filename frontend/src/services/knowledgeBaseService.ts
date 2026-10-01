import { apiClient } from "./apiClient";
import type { KnowledgeBase, KnowledgeBaseDocument } from "@/types/knowledgeBase";

export const knowledgeBaseService = {
  list: async () => {
    const { data } = await apiClient.get<KnowledgeBase[]>("/knowledge-bases");
    return data;
  },
  create: async (payload: { name: string; description?: string }) => {
    const { data } = await apiClient.post<KnowledgeBase>("/knowledge-bases", payload);
    return data;
  },
  listDocuments: async (kbId: string) => {
    const { data } = await apiClient.get<KnowledgeBaseDocument[]>(`/knowledge-bases/${kbId}/documents`);
    return data;
  },
  uploadDocument: async (kbId: string, file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const { data } = await apiClient.post<KnowledgeBaseDocument>(
      `/knowledge-bases/${kbId}/documents`,
      formData,
      { headers: { "Content-Type": "multipart/form-data" } },
    );
    return data;
  },
  reindexDocument: async (documentId: string) => {
    const { data } = await apiClient.post<KnowledgeBaseDocument>(`/documents/${documentId}/reindex`);
    return data;
  },
  deleteDocument: async (documentId: string) => {
    await apiClient.delete(`/documents/${documentId}`);
  },
};
