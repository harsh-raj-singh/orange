"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Profile = {
  name: string;
  role: string;
  company: string;
  teamProject: string;
};

type ChatMessage = {
  id: string;
  role: "user" | "assistant";
  content: string;
  memory?: MemoryReference[];
};

type MemoryReference = {
  id: string;
  label: string;
  node_type: string;
  similarity_score: number;
};

type CompletionTrigger = "user_done" | "pagehide";

type ChatResponse = {
  message?: string;
  content?: string;
  reply?: string;
  sessionId?: string;
  memory_used?: boolean;
  matches?: MemoryReference[];
};

const emptyProfile: Profile = {
  name: "",
  role: "",
  company: "",
  teamProject: "",
};

const profileFields: ReadonlyArray<{
  id: keyof Profile;
  label: string;
  placeholder: string;
  multiline?: boolean;
}> = [
  { id: "name", label: "Name", placeholder: "Avery Chen" },
  { id: "role", label: "Role", placeholder: "Staff engineer" },
  { id: "company", label: "Company", placeholder: "Acme Cloud" },
  { id: "teamProject", label: "Team or project", placeholder: "Platform reliability" },
];

function createId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getAssistantText(data: ChatResponse) {
  return data.message ?? data.content ?? data.reply ?? "I saved that turn, but the demo did not return a response.";
}

function parseServerEventBlock(block: string) {
  const event = block
    .split("\n")
    .find((line) => line.startsWith("event:"))
    ?.slice("event:".length)
    .trim();
  const data = block
    .split("\n")
    .filter((line) => line.startsWith("data:"))
    .map((line) => line.slice("data:".length).trim())
    .join("\n");

  if (!event || !data) {
    return null;
  }

  try {
    return { event, data: JSON.parse(data) as ChatResponse & { text?: string } };
  } catch {
    return null;
  }
}

export default function TestChat() {
  const [profile, setProfile] = useState<Profile>(emptyProfile);
  const [isProfileSubmitted, setIsProfileSubmitted] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sessionId, setSessionId] = useState<string>(() => createId("orange-session"));
  const [isSending, setIsSending] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSavedCount, setLastSavedCount] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const latestRef = useRef({
    profile,
    messages,
    sessionId,
    lastSavedCount,
    isProfileSubmitted,
  });

  const isProfileReady = useMemo(
    () => Object.values(profile).every((value) => value.trim().length > 0),
    [profile],
  );
  const hasUnsavedMessages = messages.length > lastSavedCount;

  useEffect(() => {
    latestRef.current = {
      profile,
      messages,
      sessionId,
      lastSavedCount,
      isProfileSubmitted,
    };
  }, [isProfileSubmitted, lastSavedCount, messages, profile, sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isSending]);

  const completeConversation = useCallback(
    async (trigger: CompletionTrigger, options?: { beacon?: boolean }) => {
      const state = latestRef.current;

      if (!state.isProfileSubmitted || state.messages.length <= state.lastSavedCount) {
        return false;
      }

      const payload = {
        profile: state.profile,
        messages: state.messages,
        sessionId: state.sessionId,
        trigger,
      };
      const body = JSON.stringify(payload);

      if (options?.beacon && typeof navigator !== "undefined" && "sendBeacon" in navigator) {
        const sent = navigator.sendBeacon(
          "/api/demo/conversations/complete",
          new Blob([body], { type: "application/json" }),
        );

        if (sent) {
          setLastSavedCount(state.messages.length);
          window.dispatchEvent(new CustomEvent("orange-memory-graph-updated"));
          return true;
        }
      }

      const response = await fetch("/api/demo/conversations/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: options?.beacon,
      });

      if (!response.ok) {
        throw new Error("Completion request failed.");
      }

      setLastSavedCount(state.messages.length);
      window.dispatchEvent(new CustomEvent("orange-memory-graph-updated"));
      return true;
    },
    [],
  );

  useEffect(() => {
    function persistBeforeExit() {
      void completeConversation("pagehide", { beacon: true }).catch(() => {
        // Navigation is already underway; keep this best-effort and quiet.
      });
    }

    window.addEventListener("pagehide", persistBeforeExit);
    window.addEventListener("beforeunload", persistBeforeExit);

    return () => {
      window.removeEventListener("pagehide", persistBeforeExit);
      window.removeEventListener("beforeunload", persistBeforeExit);
    };
  }, [completeConversation]);

  function updateProfile(field: keyof Profile, value: string) {
    setProfile((current) => ({ ...current, [field]: value }));
  }

  function submitProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    if (!isProfileReady) {
      setError("Complete each profile field to start the demo.");
      return;
    }

    setError(null);
    setIsProfileSubmitted(true);
  }

  async function sendMessage(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();

    const trimmedDraft = draft.trim();

    if (!trimmedDraft || isSending) {
      return;
    }

    const userMessage: ChatMessage = {
      id: createId("user"),
      role: "user",
      content: trimmedDraft,
    };
    const nextMessages = [...messages, userMessage];

    setMessages(nextMessages);
    setDraft("");
    setIsSending(true);
    setError(null);

    try {
      const response = await fetch("/api/demo/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile,
          messages: nextMessages,
          sessionId,
        }),
      });

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(errorBody?.error ?? "Chat request failed.");
      }

      const contentType = response.headers.get("content-type") ?? "";
      if (!contentType.includes("text/event-stream") || !response.body) {
        const data = (await response.json()) as ChatResponse;
        const assistantMessage: ChatMessage = {
          id: createId("assistant"),
          role: "assistant",
          content: getAssistantText(data),
          memory: data.memory_used ? data.matches : undefined,
        };

        if (data.sessionId) {
          setSessionId(data.sessionId);
        }

        setMessages((current) => [...current, assistantMessage]);
        return;
      }

      const assistantId = createId("assistant");
      let assistantContent = "";
      let memory: MemoryReference[] | undefined;
      setMessages((current) => [
        ...current,
        { id: assistantId, role: "assistant", content: "", memory },
      ]);

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const blocks = buffer.split("\n\n");
        buffer = blocks.pop() ?? "";

        for (const block of blocks) {
          const parsed = parseServerEventBlock(block);
          if (!parsed) {
            continue;
          }

          if (parsed.event === "memory") {
            memory = parsed.data.memory_used ? parsed.data.matches : undefined;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId ? { ...message, memory } : message,
              ),
            );
          }

          if (parsed.event === "delta" && parsed.data.text) {
            assistantContent += parsed.data.text;
            setMessages((current) =>
              current.map((message) =>
                message.id === assistantId
                  ? { ...message, content: assistantContent || " " }
                  : message,
              ),
            );
          }

          if (parsed.event === "done") {
            if (parsed.data.sessionId) {
              setSessionId(parsed.data.sessionId);
            }
            if (!assistantContent) {
              assistantContent = getAssistantText(parsed.data);
              setMessages((current) =>
                current.map((message) =>
                  message.id === assistantId ? { ...message, content: assistantContent, memory } : message,
                ),
              );
            }
          }
        }
      }
    } catch (error) {
      setMessages(nextMessages);
      setError(
        error instanceof Error
          ? error.message
          : "Orange could not reach the demo chat endpoint. Try again in a moment.",
      );
    } finally {
      setIsSending(false);
    }
  }

  async function markDone() {
    setIsCompleting(true);
    setError(null);

    try {
      await completeConversation("user_done");
    } catch {
      setError("Orange could not mark this conversation done. Your chat is still here.");
    } finally {
      setIsCompleting(false);
    }
  }

  if (!isProfileSubmitted) {
    return (
      <section className="rounded-lg border border-[#24352d]/10 bg-white p-5 shadow-[0_24px_70px_rgba(36,53,45,0.10)] sm:p-6">
        <div className="mb-5 flex flex-col gap-2 border-b border-[#24352d]/10 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#c5551c]">
              Demo profile
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-[#161b18]">Start a test session</h2>
          </div>
          <p className="font-mono text-xs text-[#5f746b]">required before chat</p>
        </div>

        <form className="grid gap-4 md:grid-cols-2" onSubmit={submitProfile}>
          {profileFields.map((field) => (
            <label htmlFor={`orange-${field.id}`} key={field.id}>
              <span className="text-sm font-semibold text-[#24352d]">{field.label}</span>
              <input
                id={`orange-${field.id}`}
                className="mt-2 h-11 w-full rounded-md border border-[#d8ded7] bg-[#fbfaf5] px-3 text-sm text-[#182019] outline-none transition placeholder:text-[#8b968f] focus:border-[#c5551c] focus:ring-2 focus:ring-[#c5551c]/18"
                placeholder={field.placeholder}
                value={profile[field.id]}
                onChange={(event) => updateProfile(field.id, event.target.value)}
                required
              />
            </label>
          ))}

          <div className="flex flex-col gap-3 border-t border-[#24352d]/10 pt-4 md:col-span-2 sm:flex-row sm:items-center sm:justify-between">
            <p aria-live="polite" className="min-h-5 text-sm text-[#9f4218]">
              {error}
            </p>
            <button
              type="submit"
              className="inline-flex h-11 items-center justify-center rounded-md bg-[#24352d] px-5 text-sm font-bold text-white shadow-[0_14px_36px_rgba(36,53,45,0.16)] transition hover:bg-[#c5551c] disabled:cursor-not-allowed disabled:opacity-55"
              disabled={!isProfileReady}
            >
              Open chat
            </button>
          </div>
        </form>
      </section>
    );
  }

  return (
    <section className="overflow-hidden rounded-lg border border-[#24352d]/10 bg-[#fbfaf5] shadow-[0_24px_70px_rgba(36,53,45,0.10)]">
      <div className="flex flex-col gap-3 border-b border-[#24352d]/10 bg-white px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#2f6f5e]">
            Test chat
          </p>
          <h2 className="mt-1 text-xl font-semibold text-[#161b18]">
            {profile.name} · {profile.teamProject}
          </h2>
        </div>
        <button
          type="button"
          className="inline-flex h-10 items-center justify-center rounded-md border border-[#24352d]/20 px-4 text-sm font-bold text-[#24352d] transition hover:border-[#c5551c] hover:text-[#c5551c] disabled:cursor-not-allowed disabled:opacity-55"
          disabled={!hasUnsavedMessages || isCompleting}
          onClick={markDone}
        >
          {isCompleting ? "Saving..." : "Mark conversation done"}
        </button>
      </div>

      <div className="grid min-h-[520px] lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="border-b border-[#24352d]/10 bg-[#f7f3e8] p-5 lg:border-b-0 lg:border-r">
          <dl className="grid gap-4 text-sm">
            <div>
              <dt className="font-mono text-xs uppercase tracking-[0.16em] text-[#8f3b14]">Role</dt>
              <dd className="mt-1 font-semibold text-[#24352d]">{profile.role}</dd>
            </div>
            <div>
              <dt className="font-mono text-xs uppercase tracking-[0.16em] text-[#8f3b14]">Company</dt>
              <dd className="mt-1 font-semibold text-[#24352d]">{profile.company}</dd>
            </div>
          </dl>
        </aside>

        <div className="flex min-h-[520px] flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5" aria-live="polite">
            {messages.length === 0 ? (
              <div className="rounded-md border border-dashed border-[#9aa79d] bg-white px-4 py-6 text-sm leading-6 text-[#536057]">
                Ask the demo about a project memory, a debugging path, or a decision you want retained.
              </div>
            ) : (
              messages.map((message) => (
                <div
                  className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
                  key={message.id}
                >
                  <article
                    className={`max-w-[min(42rem,92%)] rounded-lg border px-4 py-3 text-sm leading-6 shadow-sm ${
                      message.role === "user"
                        ? "border-[#c5551c]/30 bg-[#fff8ec] text-[#3a2418]"
                        : "border-[#d8ded7] bg-white text-[#24352d]"
                    }`}
                  >
                    <p className="mb-1 font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#5f746b]">
                      {message.role === "user" ? profile.name : "Orange"}
                    </p>
                    {message.role === "assistant" && message.memory?.length ? (
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        <span className="rounded-full border border-[#2f6f5e]/25 bg-[#f1faf5] px-2 py-1 font-mono text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-[#2f6f5e]">
                          Retrieved from memory
                        </span>
                        {message.memory.map((memoryNode) => (
                          <a
                            className="rounded-full border border-[#c5551c]/20 bg-[#fff8ec] px-2 py-1 text-xs font-semibold text-[#8f3b14] transition hover:border-[#c5551c]"
                            href="#graph"
                            key={memoryNode.id}
                            title={`${memoryNode.node_type} · score ${memoryNode.similarity_score}`}
                          >
                            {memoryNode.label}
                          </a>
                        ))}
                      </div>
                    ) : null}
                    <p className="whitespace-pre-wrap">{message.content}</p>
                  </article>
                </div>
              ))
            )}

            {isSending ? (
              <div className="max-w-40 rounded-lg border border-[#d8ded7] bg-white px-4 py-3 text-sm text-[#536057] shadow-sm">
                Orange is thinking...
              </div>
            ) : null}
            <div ref={messagesEndRef} />
          </div>

          <form className="border-t border-[#24352d]/10 bg-white p-4" onSubmit={sendMessage}>
            <label className="sr-only" htmlFor="orange-chat-message">
              Message
            </label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <textarea
                id="orange-chat-message"
                className="min-h-24 flex-1 resize-y rounded-md border border-[#d8ded7] bg-[#fbfaf5] px-3 py-3 text-sm leading-6 text-[#182019] outline-none transition placeholder:text-[#8b968f] focus:border-[#c5551c] focus:ring-2 focus:ring-[#c5551c]/18"
                placeholder="Type a message for the Orange demo..."
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && (event.metaKey || event.ctrlKey)) {
                    event.currentTarget.form?.requestSubmit();
                  }
                }}
              />
              <button
                type="submit"
                className="inline-flex h-12 items-center justify-center rounded-md bg-[#c5551c] px-5 text-sm font-bold text-white shadow-[0_14px_36px_rgba(197,85,28,0.18)] transition hover:bg-[#9f4218] disabled:cursor-not-allowed disabled:opacity-55 sm:self-end"
                disabled={!draft.trim() || isSending}
              >
                {isSending ? "Sending..." : "Send"}
              </button>
            </div>
            <p aria-live="polite" className="mt-3 min-h-5 text-sm text-[#9f4218]">
              {error}
            </p>
          </form>
        </div>
      </div>
    </section>
  );
}
