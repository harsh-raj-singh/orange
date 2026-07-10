"use client";

import { useState } from "react";

const ORANGE_MCP_URL = (
  process.env.NEXT_PUBLIC_ORANGE_MCP_URL ||
  (process.env.NEXT_PUBLIC_ORANGE_BACKEND_URL
    ? `${process.env.NEXT_PUBLIC_ORANGE_BACKEND_URL.replace(/\/$/, "")}/mcp`
    : "https://orange-api-x38s.onrender.com/mcp")
).replace(/\/$/, "");

type ClientTab = "grok" | "claude" | "chatgpt" | "generic";

const TABS: { id: ClientTab; label: string }[] = [
  { id: "grok", label: "Grok CLI" },
  { id: "claude", label: "Claude" },
  { id: "chatgpt", label: "ChatGPT" },
  { id: "generic", label: "Generic MCP" },
];

const CLIENT_SETUP: Record<
  ClientTab,
  {
    summary: string;
    commands: { label: string; value: string }[];
    steps: { title: string; body: string }[];
    tip: string;
  }
> = {
  grok: {
    summary:
      "Add the remote URL as orange-remote first so a working local stdio orange entry is not overwritten. Grok opens browser login, stores the session, and refreshes tokens—no secrets to paste.",
    commands: [
      {
        label: "Add remote (safe default name)",
        value: `grok mcp add --scope user --transport http orange-remote ${ORANGE_MCP_URL}`,
      },
      {
        label: "Optional helper",
        value: "python scripts/configure_mcp.py grok remote",
      },
    ],
    steps: [
      {
        title: "Add orange-remote",
        body: "Run the command once. The default name is orange-remote so local stdio orange is left alone.",
      },
      {
        title: "Open /mcps",
        body: "Launch Grok, enter /mcps, select orange-remote, then press i to start authentication.",
      },
      {
        title: "Browser sign-in",
        body: "Finish the Orange email login and consent, then return to Grok and verify tools.",
      },
    ],
    tip: "After remote login and tools work, promote with: grok mcp remove orange && grok mcp add --scope user --transport http orange <url>. The helper refuses to overwrite an existing name unless you pass --force.",
  },
  claude: {
    summary:
      "Point Claude Code or Claude.ai at the same Streamable HTTP URL. OAuth discovery and PKCE handle credentials in the browser.",
    commands: [
      {
        label: "Claude Code",
        value: `claude mcp add --transport http orange ${ORANGE_MCP_URL}`,
      },
      {
        label: ".mcp.json fragment",
        value: `{
  "mcpServers": {
    "orange": {
      "type": "http",
      "url": "${ORANGE_MCP_URL}"
    }
  }
}`,
      },
    ],
    steps: [
      {
        title: "Register the server",
        body: "Use the CLI command or drop the JSON fragment into your Claude MCP config.",
      },
      {
        title: "Approve access",
        body: "When Claude prompts, complete Orange sign-in and consent in the browser.",
      },
      {
        title: "Use memory tools",
        body: "Call recall_memory before work and complete_conversation when a useful session ends.",
      },
    ],
    tip: "Claude.ai custom connectors use the same URL. Do not paste a bearer token.",
  },
  chatgpt: {
    summary:
      "Connect Orange through ChatGPT Developer mode as a developer-mode App (remote MCP). This is not Custom GPT Actions.",
    commands: [
      {
        label: "MCP URL (paste into the developer-mode app)",
        value: ORANGE_MCP_URL,
      },
      {
        label: "OpenAI docs",
        value: "https://developers.openai.com/api/docs/guides/developer-mode",
      },
    ],
    steps: [
      {
        title: "Enable Developer mode",
        body: "In ChatGPT (web), open Settings → Security and login (or Settings → Apps → Advanced Settings) and turn on Developer mode. Workspace admins may need to allow this first.",
      },
      {
        title: "Create a developer-mode App",
        body: "Open Settings → Plugins (chatgpt.com/plugins) or Apps → Create. Use + to create a developer-mode app for a remote MCP server (SSE or streaming HTTP).",
      },
      {
        title: "Point at Orange + OAuth",
        body: "Paste the Orange MCP URL, choose OAuth (not a static secret), click Scan Tools, complete browser login/consent, then Create. Use the app from the composer’s Developer mode tool.",
      },
    ],
    tip: "Do not use Custom GPT Actions for Orange. ChatGPT’s MCP path is Developer mode + a developer-mode App. Write tools may ask for confirmation; Orange marks recall tools readOnlyHint.",
  },
  generic: {
    summary:
      "Any MCP client that supports Streamable HTTP + OAuth can use the same endpoint. One backend, every provider.",
    commands: [
      {
        label: "MCP URL",
        value: ORANGE_MCP_URL,
      },
      {
        label: "Config fragment",
        value: `{
  "mcpServers": {
    "orange": {
      "type": "http",
      "url": "${ORANGE_MCP_URL}"
    }
  }
}`,
      },
      {
        label: "Discovery check",
        value: `curl ${ORANGE_MCP_URL.replace(/\/mcp$/, "")}/.well-known/oauth-protected-resource/mcp`,
      },
    ],
    steps: [
      {
        title: "Point at the URL",
        body: "Configure type http (or streamable-http) with the Orange URL only.",
      },
      {
        title: "Let OAuth run",
        body: "The client discovers the resource, registers dynamically, runs PKCE, and opens the browser.",
      },
      {
        title: "Scope is automatic",
        body: "Orange scopes memory to the signed-in Supabase user. Client-supplied emails cannot impersonate another user.",
      },
    ],
    tip: "Unauthenticated POSTs to /mcp return 401 with a WWW-Authenticate resource_metadata challenge.",
  },
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
      <pre className="overflow-x-auto whitespace-pre-wrap break-words font-mono text-xs leading-5 text-[#dbe7df]">
        {value}
      </pre>
    </div>
  );
}

export default function McpConnectCard() {
  const [tab, setTab] = useState<ClientTab>("grok");
  const setup = CLIENT_SETUP[tab];

  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.05] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.28)] sm:p-6">
      <div className="flex flex-col gap-3 rounded-lg border border-emerald-300/15 bg-emerald-300/[0.07] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-white">Connect Orange—one URL for every MCP client</p>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[#cbd8cf]">
            Browser OAuth with discovery, PKCE, and dynamic client registration. Your client stores the session; you never copy a token or key.
          </p>
        </div>
        <span className="w-fit shrink-0 rounded-full border border-emerald-200/20 bg-emerald-200/10 px-3 py-1.5 font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-emerald-100">
          URL only
        </span>
      </div>

      <div className="mt-5">
        <CodeBlock label="Shared MCP endpoint" value={ORANGE_MCP_URL} />
      </div>

      <div
        role="tablist"
        aria-label="MCP client setup"
        className="mt-5 flex flex-wrap gap-2"
      >
        {TABS.map((item) => {
          const selected = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={selected}
              onClick={() => setTab(item.id)}
              className={
                selected
                  ? "rounded-md border border-[#f97316]/50 bg-[#f97316]/15 px-3 py-2 text-xs font-semibold text-white"
                  : "rounded-md border border-white/10 bg-white/[0.04] px-3 py-2 text-xs font-semibold text-[#b8c3ba] transition hover:border-white/25 hover:text-white"
              }
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div role="tabpanel" className="mt-5 space-y-4">
        <p className="text-sm leading-6 text-[#cbd8cf]">{setup.summary}</p>

        <div className="grid gap-3">
          {setup.commands.map((command) => (
            <CodeBlock key={command.label} label={command.label} value={command.value} />
          ))}
        </div>

        <ol className="grid gap-3 md:grid-cols-3">
          {setup.steps.map((step, index) => (
            <li key={step.title} className="rounded-lg border border-white/10 bg-black/20 p-4">
              <span className="font-mono text-xs font-semibold text-[#f9a66b]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <p className="mt-3 text-sm font-semibold text-white">{step.title}</p>
              <p className="mt-2 text-sm leading-6 text-[#b8c3ba]">{step.body}</p>
            </li>
          ))}
        </ol>

        <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6 text-[#dbe7df]">
          <p className="font-semibold text-white">Tip</p>
          <p className="mt-2 text-[#b8c3ba]">{setup.tip}</p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6 text-[#dbe7df]">
          <p className="font-semibold text-white">Memory protocol</p>
          <p className="mt-2">
            <span className="font-mono text-[#f9a66b]">recall_memory</span> before work,{" "}
            <span className="font-mono text-[#f9a66b]">checkpoint_context</span> for mid-session finds,{" "}
            <span className="font-mono text-[#f9a66b]">complete_conversation</span> once when done.
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6 text-[#dbe7df]">
          <p className="font-semibold text-white">Live graph refresh</p>
          <p className="mt-2">
            Nodes written through any MCP client bump the scoped graph version. The Orange UI polls that version and refreshes automatically.
          </p>
        </div>
      </div>
    </div>
  );
}
