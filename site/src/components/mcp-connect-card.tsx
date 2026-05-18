"use client";

import { useEffect, useMemo, useRef, useState } from "react";

type ConnectResponse = {
  email: string;
  name?: string | null;
  token: string;
  mcp_url: string;
  codex_config: string;
  codex_command: string;
  claude_command: string;
};

type GoogleCredentialResponse = {
  credential?: string;
};

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (config: {
            client_id: string;
            callback: (response: GoogleCredentialResponse) => void;
            ux_mode?: "popup" | "redirect";
          }) => void;
          renderButton: (
            element: HTMLElement,
            options: {
              theme?: "outline" | "filled_blue" | "filled_black";
              size?: "large" | "medium" | "small";
              type?: "standard" | "icon";
              shape?: "rectangular" | "pill" | "circle" | "square";
              text?: "signin_with" | "signup_with" | "continue_with" | "signin";
              width?: number;
            },
          ) => void;
        };
      };
    };
  }
}

const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

function CopyButton({ value }: { value: string }) {
  const [copied, setCopied] = useState(false);

  return (
    <button
      type="button"
      onClick={async () => {
        await navigator.clipboard.writeText(value);
        setCopied(true);
        window.setTimeout(() => setCopied(false), 1400);
      }}
      className="rounded-md border border-white/10 bg-white/[0.06] px-3 py-2 text-xs font-semibold text-white transition hover:border-[#f97316]/60 hover:bg-[#f97316]/15"
    >
      {copied ? "Copied" : "Copy"}
    </button>
  );
}

function CodeBlock({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-white/10 bg-black/35 p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="font-mono text-xs uppercase tracking-[0.14em] text-[#f9a66b]">{label}</p>
        <CopyButton value={value} />
      </div>
      <pre className="max-h-56 overflow-auto whitespace-pre-wrap break-words font-mono text-xs leading-5 text-[#dbe7df]">
        {value}
      </pre>
    </div>
  );
}

export default function McpConnectCard() {
  const googleButtonRef = useRef<HTMLDivElement | null>(null);
  const initializedRef = useRef(false);
  const [data, setData] = useState<ConnectResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const configPath = useMemo(() => "~/.codex/config.toml", []);

  useEffect(() => {
    if (!GOOGLE_CLIENT_ID || initializedRef.current) {
      return;
    }

    const setupGoogleButton = () => {
      if (!window.google?.accounts?.id || !googleButtonRef.current || initializedRef.current) {
        return;
      }
      initializedRef.current = true;
      window.google.accounts.id.initialize({
        client_id: GOOGLE_CLIENT_ID,
        ux_mode: "popup",
        callback: async (response) => {
          if (!response.credential) {
            setError("Google did not return a sign-in credential.");
            return;
          }
          setLoading(true);
          setError("");
          setData(null);
          try {
            const connectResponse = await fetch("/api/mcp/connect", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ credential: response.credential }),
            });
            const result = await connectResponse.json();
            if (!connectResponse.ok) {
              throw new Error(result.error || "Could not connect Orange MCP.");
            }
            setData(result as ConnectResponse);
          } catch (err) {
            setError(err instanceof Error ? err.message : "Could not connect Orange MCP.");
          } finally {
            setLoading(false);
          }
        },
      });
      window.google.accounts.id.renderButton(googleButtonRef.current, {
        theme: "filled_black",
        size: "large",
        type: "standard",
        shape: "rectangular",
        text: "continue_with",
        width: 280,
      });
    };

    if (window.google?.accounts?.id) {
      setupGoogleButton();
      return;
    }

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    script.onload = setupGoogleButton;
    script.onerror = () => setError("Could not load Google sign-in. Check NEXT_PUBLIC_GOOGLE_CLIENT_ID.");
    document.head.appendChild(script);

    return () => {
      script.remove();
    };
  }, []);

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.05] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.28)]">
      <div className="rounded-lg border border-white/10 bg-black/20 p-4">
        <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
          <div>
            <p className="text-sm font-semibold text-white">Sign in to enable Orange MCP</p>
            <p className="mt-1 text-sm leading-6 text-[#cbd8cf]">
              Orange uses your verified Google email as your private memory identity.
            </p>
          </div>
          <div className="min-h-10 min-w-[280px]">
            {GOOGLE_CLIENT_ID ? (
              <div ref={googleButtonRef} />
            ) : (
              <div className="rounded-md border border-[#ffb4a8]/30 bg-[#ffb4a8]/10 px-4 py-3 text-sm text-[#ffddd7]">
                Google Client ID is not configured.
              </div>
            )}
          </div>
        </div>
      </div>

      {loading ? <p className="mt-4 text-sm text-[#ffe3cf]">Verifying Google sign-in...</p> : null}
      {error ? <p className="mt-4 text-sm text-[#ffb4a8]">{error}</p> : null}

      {data ? (
        <div className="mt-6 space-y-4">
          <div className="rounded-lg border border-[#f97316]/25 bg-[#f97316]/10 p-4 text-sm leading-6 text-[#ffe3cf]">
            Connected as{" "}
            <span className="font-semibold text-white">{data.name ? `${data.name} (${data.email})` : data.email}</span>.
            Add the config to <span className="font-mono text-white">{configPath}</span>, then launch Codex with the token exported.
          </div>
          <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6 text-[#dbe7df]">
            <p className="font-semibold text-white">How to use Orange</p>
            <p className="mt-2">
              Ask Codex to call <span className="font-mono text-[#f9a66b]">ping_context</span> before useful work and{" "}
              <span className="font-mono text-[#f9a66b]">complete_conversation</span> once when the session is done. Orange
              stores durable insights under your verified email.
            </p>
          </div>
          <CodeBlock label="1. Add to Codex config" value={data.codex_config} />
          <CodeBlock label="2. Launch Codex" value={data.codex_command} />
          <CodeBlock label="Claude Code alternative" value={data.claude_command} />
        </div>
      ) : (
        <ol className="mt-5 grid gap-3 text-sm leading-6 text-[#cbd8cf] md:grid-cols-3">
          <li className="rounded-md bg-black/20 p-3">
            <span className="font-mono text-[#f9a66b]">1</span> Continue with Google.
          </li>
          <li className="rounded-md bg-black/20 p-3">
            <span className="font-mono text-[#f9a66b]">2</span> Copy the Codex config.
          </li>
          <li className="rounded-md bg-black/20 p-3">
            <span className="font-mono text-[#f9a66b]">3</span> Ask Codex to remember work.
          </li>
        </ol>
      )}
    </div>
  );
}
