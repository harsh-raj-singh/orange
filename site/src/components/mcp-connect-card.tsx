"use client";

import { useMemo, useState } from "react";

type ConnectResponse = {
  email: string;
  token: string;
  mcp_url: string;
  codex_config: string;
  codex_command: string;
  claude_command: string;
};

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
  const [email, setEmail] = useState("");
  const [data, setData] = useState<ConnectResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const configPath = useMemo(() => "~/.codex/config.toml", []);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLoading(true);
    setError("");
    setData(null);
    try {
      const response = await fetch("/api/mcp/connect", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });
      const result = await response.json();
      if (!response.ok) {
        throw new Error(result.error || "Could not create MCP token.");
      }
      setData(result as ConnectResponse);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not create MCP token.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.05] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.28)]">
      <form onSubmit={submit} className="grid gap-3 md:grid-cols-[1fr_auto]">
        <label className="sr-only" htmlFor="mcp-email">
          Email
        </label>
        <input
          id="mcp-email"
          type="email"
          required
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          placeholder="you@company.com"
          className="h-12 rounded-md border border-white/10 bg-black/30 px-4 text-sm text-white outline-none transition placeholder:text-white/35 focus:border-[#f97316]/70"
        />
        <button
          type="submit"
          disabled={loading}
          className="h-12 rounded-md bg-[#f97316] px-5 text-sm font-bold text-white shadow-[0_14px_36px_rgba(249,115,22,0.22)] transition hover:scale-[1.01] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {loading ? "Creating..." : "Generate setup"}
        </button>
      </form>

      {error ? <p className="mt-4 text-sm text-[#ffb4a8]">{error}</p> : null}

      {data ? (
        <div className="mt-6 space-y-4">
          <div className="rounded-lg border border-[#f97316]/25 bg-[#f97316]/10 p-4 text-sm leading-6 text-[#ffe3cf]">
            Token created for <span className="font-semibold text-white">{data.email}</span>. Add the config to{" "}
            <span className="font-mono text-white">{configPath}</span>, then launch Codex with the token exported.
          </div>
          <CodeBlock label="1. Add to Codex config" value={data.codex_config} />
          <CodeBlock label="2. Launch Codex" value={data.codex_command} />
          <CodeBlock label="Claude Code alternative" value={data.claude_command} />
        </div>
      ) : (
        <ol className="mt-5 grid gap-3 text-sm leading-6 text-[#cbd8cf] md:grid-cols-3">
          <li className="rounded-md bg-black/20 p-3">
            <span className="font-mono text-[#f9a66b]">1</span> Enter your email.
          </li>
          <li className="rounded-md bg-black/20 p-3">
            <span className="font-mono text-[#f9a66b]">2</span> Copy the Codex config.
          </li>
          <li className="rounded-md bg-black/20 p-3">
            <span className="font-mono text-[#f9a66b]">3</span> Ask Codex to call Orange.
          </li>
        </ol>
      )}
    </div>
  );
}
