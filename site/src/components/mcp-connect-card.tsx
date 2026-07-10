"use client";

import { useState } from "react";

const ORANGE_MCP_URL = "https://orange-api-production.up.railway.app/mcp";
const GROK_ADD_COMMAND = `grok mcp add --scope user --transport http orange ${ORANGE_MCP_URL}`;

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
      {copied ? "Copied" : "Copy command"}
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

const setupSteps = [
  {
    number: "1",
    title: "Add the Orange URL",
    body: "Run the command once in your terminal. There is no token, API key, or header to copy.",
  },
  {
    number: "2",
    title: "Open Grok’s MCP panel",
    body: "Launch Grok, enter /mcps, select Orange, then press i to start authentication.",
  },
  {
    number: "3",
    title: "Sign in in your browser",
    body: "Grok opens Orange’s secure login page. Finish the email sign-in and return to the CLI.",
  },
] as const;

export default function McpConnectCard() {
  return (
    <div className="rounded-lg border border-white/10 bg-white/[0.05] p-5 shadow-[0_24px_80px_rgba(0,0,0,0.28)] sm:p-6">
      <div className="flex flex-col gap-3 rounded-lg border border-emerald-300/15 bg-emerald-300/[0.07] p-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <p className="text-sm font-semibold text-white">Browser sign-in—no secrets to manage</p>
          <p className="mt-1 max-w-2xl text-sm leading-6 text-[#cbd8cf]">
            Orange uses the standard MCP OAuth flow. Grok stores the resulting session after you approve access in your browser.
          </p>
        </div>
        <span className="w-fit shrink-0 rounded-full border border-emerald-200/20 bg-emerald-200/10 px-3 py-1.5 font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-emerald-100">
          URL only
        </span>
      </div>

      <div className="mt-5">
        <CodeBlock label="Run once in your terminal" value={GROK_ADD_COMMAND} />
      </div>

      <ol className="mt-5 grid gap-3 md:grid-cols-3">
        {setupSteps.map((step) => (
          <li key={step.number} className="rounded-lg border border-white/10 bg-black/20 p-4">
            <span className="font-mono text-xs font-semibold text-[#f9a66b]">{step.number.padStart(2, "0")}</span>
            <p className="mt-3 text-sm font-semibold text-white">{step.title}</p>
            <p className="mt-2 text-sm leading-6 text-[#b8c3ba]">{step.body}</p>
          </li>
        ))}
      </ol>

      <div className="mt-5 grid gap-4 md:grid-cols-2">
        <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6 text-[#dbe7df]">
          <p className="font-semibold text-white">Inside Grok</p>
          <p className="mt-2">
            Enter <span className="font-mono text-[#f9a66b]">/mcps</span>, highlight Orange, and press{" "}
            <span className="font-mono text-[#f9a66b]">i</span>. Your browser handles the login and consent screen.
          </p>
        </div>
        <div className="rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6 text-[#dbe7df]">
          <p className="font-semibold text-white">Then use Orange naturally</p>
          <p className="mt-2">
            Ask Grok to recall relevant memory before work and call{" "}
            <span className="font-mono text-[#f9a66b]">complete_conversation</span> when a useful session is finished.
          </p>
        </div>
      </div>

      <details className="mt-5 rounded-lg border border-white/10 bg-black/20 p-4 text-sm leading-6 text-[#b8c3ba]">
        <summary className="cursor-pointer font-semibold text-white">Already configured Orange with an old token?</summary>
        <p className="mt-3">
          Run <span className="font-mono text-[#f9a66b]">grok mcp remove orange</span>, then run the URL command above again. Grok will use browser login instead of the old authorization header.
        </p>
      </details>
    </div>
  );
}
