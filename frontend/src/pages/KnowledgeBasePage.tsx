import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { knowledgeBaseService } from "@/services/knowledgeBaseService";
import type { KnowledgeBase, KnowledgeBaseDocument } from "@/types/knowledgeBase";

const STATUS_STYLES: Record<string, string> = {
  PENDING: "bg-muted text-foreground",
  PROCESSING: "bg-yellow-500/20 text-yellow-700",
  COMPLETED: "bg-green-500/20 text-green-700",
  FAILED: "bg-destructive/20 text-destructive",
};

export default function KnowledgeBasePage() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([]);
  const [selectedKbId, setSelectedKbId] = useState<string | null>(null);
  const [documents, setDocuments] = useState<KnowledgeBaseDocument[]>([]);
  const [newName, setNewName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isUploading, setIsUploading] = useState(false);

  async function loadKnowledgeBases() {
    const kbs = await knowledgeBaseService.list();
    setKnowledgeBases(kbs);
    if (!selectedKbId && kbs.length > 0) {
      setSelectedKbId(kbs[0].id);
    }
  }

  async function loadDocuments(kbId: string) {
    const docs = await knowledgeBaseService.listDocuments(kbId);
    setDocuments(docs);
  }

  useEffect(() => {
    loadKnowledgeBases().catch(() => setError("Failed to load knowledge bases."));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (selectedKbId) {
      loadDocuments(selectedKbId).catch(() => setError("Failed to load documents."));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedKbId]);

  async function handleCreateKb(e: FormEvent) {
    e.preventDefault();
    const name = newName.trim();
    if (!name) return;
    try {
      const kb = await knowledgeBaseService.create({ name });
      setNewName("");
      setKnowledgeBases((prev) => [kb, ...prev]);
      setSelectedKbId(kb.id);
    } catch {
      setError("Failed to create knowledge base.");
    }
  }

  async function handleFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file || !selectedKbId) return;
    setIsUploading(true);
    setError(null);
    try {
      const doc = await knowledgeBaseService.uploadDocument(selectedKbId, file);
      setDocuments((prev) => [doc, ...prev]);
    } catch {
      setError("Failed to upload document.");
    } finally {
      setIsUploading(false);
      e.target.value = "";
    }
  }

  async function handleReindex(documentId: string) {
    try {
      const updated = await knowledgeBaseService.reindexDocument(documentId);
      setDocuments((prev) => prev.map((d) => (d.id === documentId ? updated : d)));
    } catch {
      setError("Failed to reindex document.");
    }
  }

  async function handleDelete(documentId: string) {
    try {
      await knowledgeBaseService.deleteDocument(documentId);
      setDocuments((prev) => prev.filter((d) => d.id !== documentId));
    } catch {
      setError("Failed to delete document.");
    }
  }

  return (
    <div className="min-h-screen bg-background px-6 py-8 text-foreground">
      <div className="mx-auto flex max-w-4xl items-center justify-between">
        <h1 className="text-xl font-semibold">Knowledge Base</h1>
        <Link to="/chat" className="text-sm text-primary hover:underline">
          Back to chat
        </Link>
      </div>

      {error && (
        <p role="alert" className="mx-auto mt-4 max-w-4xl text-sm text-destructive">
          {error}
        </p>
      )}

      <div className="mx-auto mt-6 grid max-w-4xl gap-6 md:grid-cols-[240px_1fr]">
        <aside className="space-y-4">
          <form onSubmit={handleCreateKb} className="space-y-2">
            <label htmlFor="kb-name" className="text-sm font-medium">
              New knowledge base
            </label>
            <Input
              id="kb-name"
              placeholder="e.g. Product FAQ"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
            />
            <Button type="submit" className="w-full" disabled={!newName.trim()}>
              Create
            </Button>
          </form>

          <ul className="space-y-1">
            {knowledgeBases.map((kb) => (
              <li key={kb.id}>
                <button
                  type="button"
                  onClick={() => setSelectedKbId(kb.id)}
                  className={`w-full rounded-md px-3 py-2 text-left text-sm ${
                    selectedKbId === kb.id ? "bg-primary text-primary-foreground" : "hover:bg-muted"
                  }`}
                >
                  {kb.name}
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <section>
          {selectedKbId ? (
            <>
              <label className="mb-3 inline-flex cursor-pointer items-center gap-2">
                <span className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground">
                  {isUploading ? "Uploading…" : "Upload document"}
                </span>
                <input
                  type="file"
                  accept=".pdf,.txt,.md,.csv"
                  className="hidden"
                  disabled={isUploading}
                  onChange={handleFileChange}
                />
              </label>

              <ul className="divide-y divide-border rounded-md border border-border">
                {documents.length === 0 && (
                  <li className="px-4 py-3 text-sm text-muted-foreground">No documents yet.</li>
                )}
                {documents.map((doc) => (
                  <li key={doc.id} className="flex items-center justify-between gap-4 px-4 py-3">
                    <div>
                      <p className="text-sm font-medium">{doc.filename}</p>
                      {doc.error_message && (
                        <p className="text-xs text-destructive">{doc.error_message}</p>
                      )}
                    </div>
                    <div className="flex items-center gap-2">
                      <span
                        className={`rounded-full px-2 py-1 text-xs font-medium ${
                          STATUS_STYLES[doc.status] ?? "bg-muted"
                        }`}
                      >
                        {doc.status}
                      </span>
                      <Button variant="secondary" onClick={() => handleReindex(doc.id)}>
                        Reindex
                      </Button>
                      <Button variant="ghost" onClick={() => handleDelete(doc.id)}>
                        Delete
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </>
          ) : (
            <p className="text-sm text-muted-foreground">Create a knowledge base to get started.</p>
          )}
        </section>
      </div>
    </div>
  );
}
