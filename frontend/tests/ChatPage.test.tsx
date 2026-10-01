import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import ChatPage from "@/pages/ChatPage";
import { AuthProvider } from "@/hooks/useAuth";
import { authService } from "@/services/authService";
import { chatService } from "@/services/chatService";
import { tokenStorage } from "@/services/apiClient";

vi.mock("@/services/authService", () => ({
  authService: {
    login: vi.fn(),
    signup: vi.fn(),
    me: vi.fn(),
  },
}));

vi.mock("@/services/chatService", () => ({
  chatService: {
    sendMessage: vi.fn(),
  },
}));

function renderChat() {
  return render(
    <MemoryRouter initialEntries={["/chat"]}>
      <AuthProvider>
        <ChatPage />
      </AuthProvider>
    </MemoryRouter>,
  );
}

describe("ChatPage", () => {
  beforeEach(() => {
    localStorage.clear();
    tokenStorage.setTokens("access-token", "refresh-token");
    vi.mocked(authService.me).mockResolvedValue({
      id: "user-1",
      email: "customer@example.com",
      role: "customer",
      organization_id: "org-1",
    });
  });

  it("sends a message and renders the assistant reply", async () => {
    vi.mocked(chatService.sendMessage).mockResolvedValue({
      message_id: "msg-1",
      conversation_id: "conv-1",
      answer: "Hello! How can I help you today?",
      confidence: null,
      sources: [],
      intent: null,
      escalated: false,
    });

    renderChat();

    await waitFor(() => expect(screen.getByText(/customer@example.com/i)).toBeInTheDocument());

    const input = screen.getByLabelText(/message/i);
    await userEvent.type(input, "Hi there");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText("Hi there")).toBeInTheDocument();
    expect(await screen.findByText(/hello! how can i help you today/i)).toBeInTheDocument();
  });

  it("shows a friendly error when the assistant is not configured (503)", async () => {
    vi.mocked(chatService.sendMessage).mockRejectedValue({ response: { status: 503 } });

    renderChat();
    await waitFor(() => expect(screen.getByText(/customer@example.com/i)).toBeInTheDocument());

    const input = screen.getByLabelText(/message/i);
    await userEvent.type(input, "Hi there");
    await userEvent.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/not configured yet/i);
  });
});
