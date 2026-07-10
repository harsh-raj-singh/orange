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
  { id: "generic", label: "Other clients" },
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
      "Add Orange as a separate remote server, then authenticate once in Grok. Your existing local server stays untouched.",
    commands: [
      {
        label: "Run in your terminal",
        value: `grok mcp add --scope user --transport http orange-remote ${ORANGE_MCP_URL}`,
      },
      {
        label: "Verify after sign-in",
        value: "grok mcp doctor orange-remote --json",
      },
    ],
    steps: [
      {
        title: "Add the remote server",
        body: "Run the command above. It registers the shared Orange endpoint as orange-remote.",
      },
      {
        title: "Authenticate in Grok",
        body: "Open /mcps, choose orange-remote, and press i. Grok opens the Orange sign-in page.",
      },
      {
        title: "Confirm the connection",
        body: "Return to Grok and ask it to call orange_status. A healthy connection exposes 11 tools.",
      },
    ],
    tip: "Keep the name orange-remote while testing. Rename it only after browser login and a memory write both succeed.",
  },
  claude: {
    summary:
      "Claude Code and Claude.ai use the same endpoint and the same per-user browser sign-in.",
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
        title: "Add Orange",
        body: "Run the Claude Code command, or add the JSON block to your project MCP configuration.",
      },
      {
        title: "Connect your account",
        body: "Open /mcp in Claude Code and complete the Orange browser sign-in when prompted.",
      },
      {
        title: "Test one recall",
        body: "Ask Claude to call orange_status, then recall_memory for the task you are about to start.",
      },
    ],
    tip: "In Claude.ai, add the URL under Customize → Connectors → Add custom connector. Leave client credentials empty unless your workspace requires them.",
  },
  chatgpt: {
    summary:
      "Add Orange as a developer-mode App. ChatGPT scans the MCP tools and sends you through the same Orange sign-in.",
    commands: [
      {
        label: "Paste this MCP URL",
        value: ORANGE_MCP_URL,
      },
    ],
    steps: [
      {
        title: "Enable Developer mode",
        body: "In ChatGPT web, open Settings → Security and login and enable Developer mode.",
      },
      {
        title: "Create the Orange app",
        body: "Open Settings → Plugins/Apps, create a developer-mode app, and paste the URL above.",
      },
      {
        title: "Scan and sign in",
        body: "Choose OAuth, scan tools, complete Orange sign-in, and create the app. Then enable Orange from the chat composer.",
      },
    ],
    tip: "Orange is an MCP app, not a Custom GPT Action. ChatGPT may ask for confirmation before write tools save memory.",
  },
  generic: {
    summary:
      "Any client that supports Streamable HTTP and MCP OAuth can connect without an Orange-specific plugin.",
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
        title: "Add the endpoint",
        body: "Configure an HTTP or streamable-http MCP server using the Orange URL only.",
      },
      {
        title: "Complete sign-in",
        body: "A compatible client discovers OAuth automatically and opens the Orange login page.",
      },
      {
        title: "Verify the tools",
        body: "Call orange_status. Orange uses the verified account—not a client-supplied email—to scope private memory.",
      },
    ],
    tip: "If your client asks for a static token instead of opening a browser, it does not support Orange’s remote OAuth flow yet.",
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
    <div className="overflow-hidden rounded-2xl border border-white/10 bg-[#101713]/90 shadow-[0_30px_100px_rgba(0,0,0,0.34)]">
      <div className="flex flex-col gap-4 border-b border-white/10 bg-[linear-gradient(120deg,rgba(249,115,22,0.12),rgba(98,212,156,0.05))] p-5 sm:flex-row sm:items-center sm:justify-between sm:p-7">
        <div>
          <p className="text-lg font-semibold text-white">One endpoint, one account, the same memory everywhere.</p>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[#cbd8cf]">
            Choose your client below. You will add the URL, sign in in your browser, and verify the connection with one tool call.
          </p>
        </div>
        <span className="inline-flex w-fit shrink-0 items-center gap-2 rounded-full border border-emerald-200/20 bg-emerald-200/10 px-3 py-1.5 font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-emerald-100">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-300" /> No keys to copy
        </span>
      </div>

      <div className="px-5 pt-5 sm:px-7 sm:pt-7">
        <CodeBlock label="Shared MCP endpoint" value={ORANGE_MCP_URL} />
      </div>

      <div
        role="tablist"
        aria-label="MCP client setup"
        className="mx-5 mt-5 grid grid-cols-2 gap-2 rounded-xl border border-white/10 bg-black/20 p-1.5 sm:mx-7 sm:grid-cols-4"
      >
        {TABS.map((item) => {
          const selected = tab === item.id;
          return (
            <button
              key={item.id}
              type="button"
              role="tab"
              id={`mcp-tab-${item.id}`}
              aria-controls={`mcp-panel-${item.id}`}
              aria-selected={selected}
              onClick={() => setTab(item.id)}
              className={
                selected
                  ? "rounded-lg bg-[#f97316] px-3 py-2.5 text-xs font-semibold text-white shadow-[0_10px_28px_rgba(249,115,22,0.22)]"
                  : "rounded-lg px-3 py-2.5 text-xs font-semibold text-[#9eaaa2] transition hover:bg-white/[0.05] hover:text-white"
              }
            >
              {item.label}
            </button>
          );
        })}
      </div>

      <div
        role="tabpanel"
        id={`mcp-panel-${tab}`}
        aria-labelledby={`mcp-tab-${tab}`}
        className="grid gap-6 p-5 sm:p-7 lg:grid-cols-[0.9fr_1.1fr]"
      >
        <div>
          <p className="text-base leading-7 text-[#d8e2da]">{setup.summary}</p>

          <div className="mt-5 grid gap-3">
          {setup.commands.map((command) => (
            <CodeBlock key={command.label} label={command.label} value={command.value} />
          ))}
          </div>

          <div className="mt-4 rounded-xl border border-[#f97316]/20 bg-[#f97316]/[0.07] p-4 text-sm leading-6 text-[#dbe7df]">
            <p className="font-semibold text-[#ffc28f]">Good to know</p>
            <p className="mt-1 text-[#b8c3ba]">{setup.tip}</p>
          </div>
        </div>

        <ol className="grid gap-3">
          {setup.steps.map((step, index) => (
            <li key={step.title} className="grid grid-cols-[2.25rem_1fr] gap-3 rounded-xl border border-white/10 bg-white/[0.035] p-4">
              <span className="flex h-9 w-9 items-center justify-center rounded-full border border-[#f97316]/30 bg-[#f97316]/10 font-mono text-xs font-semibold text-[#f9a66b]">
                {String(index + 1).padStart(2, "0")}
              </span>
              <div>
                <p className="text-sm font-semibold text-white">{step.title}</p>
                <p className="mt-1 text-sm leading-6 text-[#aebbb2]">{step.body}</p>
              </div>
            </li>
          ))}
        </ol>
      </div>

      <div className="grid gap-px border-t border-white/10 bg-white/10 md:grid-cols-2">
        <div className="bg-[#0d1210] p-5 text-sm leading-6 text-[#dbe7df] sm:p-6">
          <p className="font-semibold text-white">How agents use Orange</p>
          <p className="mt-2">
            Recall before starting, checkpoint a critical finding, and complete the conversation once useful work is finished.
          </p>
        </div>
        <div className="bg-[#0d1210] p-5 text-sm leading-6 text-[#dbe7df] sm:p-6">
          <p className="font-semibold text-white">What stays consistent</p>
          <p className="mt-2">
            Every client writes to the same scoped Postgres graph. New nodes appear in the Orange UI without a manual refresh.
          </p>
        </div>
      </div>
    </div>
  );
}
