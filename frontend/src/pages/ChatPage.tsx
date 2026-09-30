import { useRef, useState } from "react";
import type { FormEvent } from "react";
import { useAuth } from "@/hooks/useAuth";
import { Button } from "@/components/ui/Button";
import { chatService } from "@/services/chatService";
import type { ChatMessage } from "@/types/chat";

function newId() {
  return typeof crypto.randomUUID === "function" ? crypto.randomUUID() : Math.random().toString(36).slice(2);
}

export default function ChatPage() {
  const { user, logout } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const text = input.trim();
    if (!text || isSending) return;

    const userMessage: ChatMessage = { id: newId(), sender: "customer", content: text };
    setMessages((prev) => [...prev, userMessage]);
    setInput("");
    setError(null);
    setIsSending(true);

    try {
      const response = await chatService.sendMessage({
        conversation_id: conversationId,
        message: text,
      });
      setConversationId(response.conversation_id);
      setMessages((prev) => [
        ...prev,
        { id: response.message_id, sender: "assistant", content: response.answer, sources: response.sources },
      ]);
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 503) {
        setError("The assistant is not configured yet. An administrator needs to add an OpenAI API key.");
      } else {
        setError("Something went wrong sending your message. Please try again.");
      }
    } finally {
      setIsSending(false);
      setTimeout(() => bottomRef.current?.scrollIntoView?.({ behavior: "smooth" }), 0);
    }
  }

  return (
    <div className="flex min-h-screen flex-col bg-background text-foreground">
      <header className="flex items-center justify-between border-b border-border px-6 py-4">
        <div>
          <h1 className="text-lg font-semibold">AICSP Support Chat</h1>
          {user && <p className="text-sm text-muted-foreground">Signed in as {user.email}</p>}
        </div>
        <Button variant="secondary" onClick={() => logout()}>
          Sign out
        </Button>
      </header>

      <main className="flex flex-1 flex-col overflow-y-auto px-6 py-4">
        {messages.length === 0 && (
          <p className="m-auto text-sm text-muted-foreground">
            Start the conversation by sending a message below.
          </p>
        )}
        <ul className="flex flex-1 flex-col gap-3">
          {messages.map((message) => (
            <li
              key={message.id}
              className={
                message.sender === "customer"
                  ? "ml-auto max-w-lg rounded-lg bg-primary px-4 py-2 text-sm text-primary-foreground"
                  : "mr-auto max-w-lg rounded-lg bg-muted px-4 py-2 text-sm text-foreground"
              }
            >
              <p>{message.content}</p>
              {message.sources && message.sources.length > 0 && (
                <ul className="mt-2 space-y-1 border-t border-border/50 pt-2 text-xs text-muted-foreground">
                  {message.sources.map((source, index) => (
                    <li key={source.chunk_id}>
                      [{index + 1}] {source.snippet}
                    </li>
                  ))}
                </ul>
              )}
            </li>
          ))}
        </ul>
        <div ref={bottomRef} />
      </main>

      {error && (
        <p role="alert" className="px-6 pb-2 text-sm text-destructive">
          {error}
        </p>
      )}

      <form onSubmit={handleSubmit} className="flex items-center gap-2 border-t border-border px-6 py-4">
        <input
          aria-label="Message"
          className="flex h-10 flex-1 rounded-md border border-border bg-background px-3 text-sm outline-none focus:ring-2 focus:ring-ring"
          placeholder="Type your message…"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          disabled={isSending}
        />
        <Button type="submit" isLoading={isSending} disabled={!input.trim()}>
          Send
        </Button>
      </form>
    </div>
  );
}
