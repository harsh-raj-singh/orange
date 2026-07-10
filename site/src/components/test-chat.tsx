"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";

type Profile = {
  name: string;
  email: string;
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
  scope?: string;
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

type CompletionResponse = {
  persisted?: boolean;
  source?: "backend";
  job_status?: string;
};

const emptyProfile: Profile = {
  name: "",
  email: "",
  role: "",
  company: "",
  teamProject: "",
};

const profileFields: ReadonlyArray<{
  id: keyof Profile;
  label: string;
  placeholder: string;
  type?: string;
  multiline?: boolean;
}> = [
  { id: "company", label: "Company memory space", placeholder: "Acme Cloud" },
];

const starterPrompts = [
  "We fixed a CORS preflight failure by moving middleware before the router.",
  "Remember that we chose Supabase session pooling for IPv4 hosting.",
  "What context do you already have about the Orange MCP migration?",
];

function createId(prefix: string) {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return `${prefix}-${crypto.randomUUID()}`;
  }

  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function getAssistantText(data: ChatResponse) {
  return data.message ?? data.content ?? data.reply ?? "The turn was received, but Orange did not return a chat response.";
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

function memoryScopeFor(memoryNode: MemoryReference) {
  const scope = memoryNode.scope?.toLowerCase();

  if (scope === "global" || scope === "shared") {
    return "shared";
  }

  return "private";
}

function memoryChipLabel(memoryNode: MemoryReference) {
  return memoryScopeFor(memoryNode) === "shared" ? "From shared knowledge" : "From your sessions";
}

function memoryChipClass(memoryNode: MemoryReference) {
  return memoryScopeFor(memoryNode) === "shared"
    ? "border-[#6f61b5]/25 bg-[#f5f2ff] text-[#55479a] hover:border-[#6f61b5]"
    : "border-[#c5551c]/20 bg-[#fff8ec] text-[#8f3b14] hover:border-[#c5551c]";
}

export default function TestChat({ authenticatedEmail }: { authenticatedEmail: string | null }) {
  const verifiedEmail = authenticatedEmail?.trim().toLowerCase() ?? "";
  const [profile, setProfile] = useState<Profile>(() => {
    const verifiedProfile = { ...emptyProfile, email: verifiedEmail };

    if (typeof window === "undefined") {
      return verifiedProfile;
    }

    try {
      const storedProfile = window.localStorage.getItem("orange-demo-profile");
      if (!storedProfile) {
        return verifiedProfile;
      }
      const parsed = JSON.parse(storedProfile) as Partial<Profile>;
      return {
        ...verifiedProfile,
        company: typeof parsed.company === "string" ? parsed.company : "",
        name: typeof parsed.name === "string" ? parsed.name : "",
        role: typeof parsed.role === "string" ? parsed.role : "",
        teamProject: typeof parsed.teamProject === "string" ? parsed.teamProject : "",
      };
    } catch {
      return verifiedProfile;
    }
  });
  const [contributeToGlobal, setContributeToGlobal] = useState(true);
  const [isProfileSubmitted, setIsProfileSubmitted] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"queued" | "backend" | null>(null);
  const [profileAttempted, setProfileAttempted] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [sessionId, setSessionId] = useState<string>(() => createId("orange-session"));
  const [isSending, setIsSending] = useState(false);
  const [isCompleting, setIsCompleting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSavedCount, setLastSavedCount] = useState(0);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const authenticatedProfile = useMemo(
    () => ({ ...profile, email: verifiedEmail }),
    [profile, verifiedEmail],
  );
  const latestRef = useRef({
    profile: authenticatedProfile,
    messages,
    sessionId,
    lastSavedCount,
    isProfileSubmitted,
    contributeToGlobal,
  });

  const isProfileReady = useMemo(
    () => verifiedEmail.length > 0 && profile.company.trim().length > 0,
    [profile.company, verifiedEmail],
  );
  const hasUnsavedMessages = messages.length > lastSavedCount;

  useEffect(() => {
    latestRef.current = {
      profile: authenticatedProfile,
      messages,
      sessionId,
      lastSavedCount,
      isProfileSubmitted,
      contributeToGlobal,
    };
  }, [authenticatedProfile, contributeToGlobal, isProfileSubmitted, lastSavedCount, messages, sessionId]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ block: "end" });
  }, [messages, isSending]);

  const completeConversation = useCallback(
    async (trigger: CompletionTrigger, options?: { beacon?: boolean }) => {
      const state = latestRef.current;

      if (!state.isProfileSubmitted || state.messages.length <= state.lastSavedCount) {
        return null;
      }

      const payload = {
        profile: state.profile,
        messages: state.messages,
        sessionId: state.sessionId,
        trigger,
        contribute_to_global: state.contributeToGlobal,
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
          return null;
        }
      }

      const response = await fetch("/api/demo/conversations/complete", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body,
        keepalive: options?.beacon,
      });

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(errorBody?.error ?? "Orange could not save this session.");
      }

      const completion = (await response.json().catch(() => ({}))) as CompletionResponse;
      setLastSavedCount(state.messages.length);
      window.dispatchEvent(new CustomEvent("orange-memory-graph-updated"));
      return completion;
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
    if (field === "company" && value.trim()) {
      setError(null);
    }
  }

  function submitProfile(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setProfileAttempted(true);

    if (!isProfileReady) {
      setError("Enter the shared workspace name to start the session.");
      return;
    }

    window.localStorage.setItem("orange-demo-profile", JSON.stringify(authenticatedProfile));
    window.dispatchEvent(new CustomEvent("orange-demo-profile-updated"));
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
    setSaveStatus(null);
    setError(null);

    try {
      const response = await fetch("/api/demo/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          profile: authenticatedProfile,
          messages: nextMessages,
          sessionId,
          contribute_to_global: contributeToGlobal,
        }),
      });

      if (!response.ok) {
        const errorBody = (await response.json().catch(() => null)) as { error?: string } | null;
        throw new Error(errorBody?.error ?? "Orange could not send this message. Please try again.");
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
      let animationFrame = 0;
      const syncAssistantMessage = () => {
        animationFrame = 0;
        setMessages((current) =>
          current.map((message) =>
            message.id === assistantId
              ? { ...message, content: assistantContent || " ", memory }
              : message,
          ),
        );
      };
      const scheduleAssistantSync = () => {
        if (animationFrame) {
          return;
        }
        animationFrame = window.requestAnimationFrame(syncAssistantMessage);
      };
      const applyServerEventBlock = (block: string) => {
        const parsed = parseServerEventBlock(block);
        if (!parsed) {
          return;
        }

        if (parsed.event === "memory") {
          memory = parsed.data.memory_used ? parsed.data.matches : undefined;
          scheduleAssistantSync();
          return;
        }

        if (parsed.event === "delta" && parsed.data.text) {
          assistantContent += parsed.data.text;
          scheduleAssistantSync();
          return;
        }

        if (parsed.event === "done") {
          if (parsed.data.sessionId) {
            setSessionId(parsed.data.sessionId);
          }
          if (!assistantContent) {
            assistantContent = getAssistantText(parsed.data);
          }
          scheduleAssistantSync();
        }
      };
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
          applyServerEventBlock(block);
        }
      }

      if (buffer.trim()) {
        applyServerEventBlock(buffer);
      }
      if (animationFrame) {
        window.cancelAnimationFrame(animationFrame);
        syncAssistantMessage();
      }
    } catch (error) {
      setMessages(nextMessages);
      setError(
        error instanceof Error
          ? error.message
          : "Orange could not reach the chat service. Try again in a moment.",
      );
    } finally {
      setIsSending(false);
    }
  }

  async function markDone() {
    setIsCompleting(true);
    setError(null);

    try {
      const completion = await completeConversation("user_done");
      setSaveStatus(
        completion?.persisted === false
          ? null
          : completion?.job_status && completion.job_status !== "succeeded"
            ? "queued"
            : "backend",
      );
    } catch (saveError) {
      setError(
        saveError instanceof Error
          ? `${saveError.message} Your conversation is still available here.`
          : "Orange could not save this session yet. Your conversation is still available here.",
      );
    } finally {
      setIsCompleting(false);
    }
  }

  if (!verifiedEmail) {
    return (
      <section className="rounded-lg border border-[#24352d]/10 bg-white p-6 shadow-[0_24px_70px_rgba(36,53,45,0.10)] sm:p-8">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#c5551c]">
          Sign in to try Orange
        </p>
        <h2 className="mt-3 text-2xl font-semibold text-[#161b18]">
          Use your own memory, not the public preview.
        </h2>
        <p className="mt-3 max-w-2xl text-sm leading-6 text-[#536057]">
          The graph above is sample data. Sign in to create private memories, recall them in chat, and watch your own graph update.
        </p>
        <a
          href="/login?next=%2F%23try"
          className="mt-6 inline-flex h-11 items-center justify-center rounded-md bg-[#24352d] px-5 text-sm font-bold text-white transition hover:bg-[#c5551c]"
        >
          Sign in with email
        </a>
      </section>
    );
  }

  if (!isProfileSubmitted) {
    return (
      <section className="rounded-lg border border-[#24352d]/10 bg-white p-5 shadow-[0_24px_70px_rgba(36,53,45,0.10)] sm:p-6">
        <div className="mb-5 flex flex-col gap-2 border-b border-[#24352d]/10 pb-4 sm:flex-row sm:items-end sm:justify-between">
          <div>
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#c5551c]">
              Set up this test session
            </p>
            <h2 className="mt-2 text-2xl font-semibold text-[#161b18]">Choose where this memory belongs.</h2>
          </div>
          <p className="font-mono text-xs text-[#5f746b]">verified account · scoped storage</p>
        </div>

        <form className="grid gap-4 md:grid-cols-2" onSubmit={submitProfile}>
          <div>
            <span className="text-sm font-semibold text-[#24352d]">Signed in as</span>
            <div className="mt-2 flex h-11 items-center rounded-md border border-[#b9d4c7] bg-[#f1faf5] px-3 text-sm font-semibold text-[#2f6f5e]">
              {verifiedEmail}
            </div>
          </div>
          {profileFields.map((field) => (
            <label htmlFor={`orange-${field.id}`} key={field.id}>
              <span className="flex items-center justify-between gap-3 text-sm font-semibold text-[#24352d]">
                {field.label}
                <span className="font-mono text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-[#8f3b14]">
                  Required
                </span>
              </span>
              <input
                id={`orange-${field.id}`}
                type={field.type ?? "text"}
                aria-describedby="orange-workspace-help"
                aria-invalid={profileAttempted && !profile.company.trim()}
                className={`mt-2 h-11 w-full rounded-md border bg-[#fbfaf5] px-3 text-sm text-[#182019] outline-none transition placeholder:text-[#8b968f] focus:border-[#c5551c] focus:ring-2 focus:ring-[#c5551c]/18 ${
                  profileAttempted && !profile.company.trim() ? "border-[#c5551c]" : "border-[#d8ded7]"
                }`}
                placeholder={field.placeholder}
                value={profile[field.id]}
                onChange={(event) => updateProfile(field.id, event.target.value)}
                required
              />
              <span id="orange-workspace-help" className="mt-2 block text-xs leading-5 text-[#66736b]">
                Everyone who joins this same workspace sees its shared graph notes.
              </span>
            </label>
          ))}

          <label className="flex gap-3 rounded-md border border-[#d8ded7] bg-[#fbfaf5] p-3 md:col-span-2">
            <input
              type="checkbox"
              className="mt-1 h-4 w-4 rounded border-[#9aa79d] text-[#c5551c] focus:ring-[#c5551c]"
              checked={contributeToGlobal}
              onChange={(event) => setContributeToGlobal(event.target.checked)}
            />
            <span>
              <span className="block text-sm font-semibold text-[#24352d]">
                Also save reusable technical insights to company memory
              </span>
              <span className="mt-1 block text-xs text-[#5f746b]">
                Private facts stay in your personal scope. Only durable, reusable knowledge is eligible for the company graph.
              </span>
            </span>
          </label>

          <div className="flex flex-col gap-3 border-t border-[#24352d]/10 pt-4 md:col-span-2 sm:flex-row sm:items-center sm:justify-between">
            <p aria-live="polite" className="min-h-5 text-sm text-[#9f4218]">
              {error}
            </p>
            <button
              type="submit"
              className="inline-flex h-11 items-center justify-center rounded-md bg-[#24352d] px-5 text-sm font-bold text-white shadow-[0_14px_36px_rgba(36,53,45,0.16)] transition hover:bg-[#c5551c] disabled:cursor-not-allowed disabled:opacity-55"
            >
              Start memory session
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
            Memory capture session
          </p>
          <h2 className="mt-1 text-xl font-semibold text-[#161b18]">
            {verifiedEmail} · {profile.company}
          </h2>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          <button
            type="button"
            className="inline-flex h-10 items-center justify-center rounded-md border border-[#24352d]/20 px-4 text-sm font-bold text-[#24352d] transition hover:border-[#c5551c] hover:text-[#c5551c] disabled:cursor-not-allowed disabled:opacity-55"
            disabled={!hasUnsavedMessages || isCompleting || isSending}
            onClick={markDone}
          >
            {isCompleting ? "Saving memory..." : "Finish & save memory"}
          </button>
          <p
            className={`text-xs ${
              saveStatus === "backend"
                  ? "text-[#2f6f5e]"
                  : saveStatus === "queued"
                    ? "text-[#9a5c16]"
                  : hasUnsavedMessages
                    ? "text-[#5f746b]"
                    : "text-transparent"
            }`}
          >
            {saveStatus === "queued"
                ? "Saved. Orange is extracting graph notes now."
                : saveStatus === "backend"
                  ? "Saved. The graph will refresh automatically."
                : hasUnsavedMessages
                  ? "Finish the session to extract durable memory."
                  : "."}
          </p>
        </div>
      </div>

      <div className="grid min-h-[520px] lg:grid-cols-[260px_minmax(0,1fr)]">
        <aside className="border-b border-[#24352d]/10 bg-[#f7f3e8] p-5 lg:border-b-0 lg:border-r">
          <dl className="grid gap-4 text-sm">
            <div>
              <dt className="font-mono text-xs uppercase tracking-[0.16em] text-[#8f3b14]">Memory space</dt>
              <dd className="mt-1 font-semibold text-[#24352d]">{profile.company}</dd>
            </div>
            <div>
              <dt className="font-mono text-xs uppercase tracking-[0.16em] text-[#8f3b14]">Email</dt>
              <dd className="mt-1 font-semibold text-[#24352d]">{verifiedEmail}</dd>
            </div>
            <div>
              <dt className="font-mono text-xs uppercase tracking-[0.16em] text-[#8f3b14]">Write scope</dt>
              <dd className="mt-1 font-semibold text-[#24352d]">
                {contributeToGlobal ? "Private + company insights" : "Private memory only"}
              </dd>
            </div>
          </dl>
        </aside>

        <div className="flex min-h-[520px] flex-col">
          <div className="flex-1 space-y-4 overflow-y-auto px-5 py-5" aria-live="polite">
            {messages.length === 0 ? (
              <div className="rounded-lg border border-dashed border-[#9aa79d] bg-white px-5 py-6 text-sm leading-6 text-[#536057]">
                <p className="font-semibold text-[#24352d]">Start with something worth remembering.</p>
                <p className="mt-1">Describe a decision or fix, or ask Orange what it already knows.</p>
                <div className="mt-4 flex flex-wrap gap-2">
                  {starterPrompts.map((prompt) => (
                    <button
                      key={prompt}
                      type="button"
                      onClick={() => setDraft(prompt)}
                      className="rounded-full border border-[#24352d]/12 bg-[#f7f3e8] px-3 py-1.5 text-left text-xs font-medium text-[#3f4b44] transition hover:border-[#c5551c]/40 hover:text-[#8f3b14]"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
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
                      {message.role === "user" ? verifiedEmail || "You" : "Orange"}
                    </p>
                    {message.role === "assistant" && message.memory?.length ? (
                      <div className="mb-2 flex flex-wrap gap-1.5">
                        <span className="rounded-full border border-[#2f6f5e]/25 bg-[#f1faf5] px-2 py-1 font-mono text-[0.65rem] font-semibold uppercase tracking-[0.12em] text-[#2f6f5e]">
                          Retrieved from memory
                        </span>
                        {message.memory.map((memoryNode) => (
                          <a
                            className={`rounded-full border px-2 py-1 text-xs font-semibold transition ${memoryChipClass(memoryNode)}`}
                            href="#graph"
                            key={memoryNode.id}
                            title={`${memoryNode.node_type} · score ${memoryNode.similarity_score}`}
                          >
                            {memoryChipLabel(memoryNode)} · {memoryNode.label}
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
                Orange is checking memory...
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
                placeholder="Describe a decision, fix, or question worth carrying forward..."
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
                {isSending ? "Working..." : "Send message"}
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
