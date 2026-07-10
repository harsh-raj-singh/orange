import Link from "next/link";

import McpConnectCard from "@/components/mcp-connect-card";

export const metadata = {
  title: "Connect an MCP client | Orange",
  description:
    "Connect Grok, Claude, ChatGPT, or another MCP client to Orange with one URL and browser sign-in.",
};

export default function McpPage() {
  return (
    <main className="relative min-h-screen overflow-hidden bg-[#0a0f0c] text-white">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_12%_8%,rgba(249,115,22,0.18),transparent_28%),radial-gradient(circle_at_88%_34%,rgba(98,212,156,0.08),transparent_32%)]" />
      <div className="relative mx-auto flex min-h-screen max-w-6xl flex-col px-5 py-7 sm:px-8">
        <header className="flex items-center justify-between border-b border-white/10 pb-5">
          <Link href="/" className="flex items-center gap-2 font-mono text-sm font-semibold tracking-[0.08em]">
            <span className="h-2.5 w-2.5 rounded-full bg-[#f97316] shadow-[0_0_20px_rgba(249,115,22,0.7)]" />
            ORANGE
          </Link>
          <div className="flex items-center gap-4 text-sm">
            <Link href="/#graph" className="hidden text-[#9eaaa2] transition hover:text-white sm:inline">View graph</Link>
            <Link href="/" className="rounded-lg border border-white/15 px-3.5 py-2 text-[#e6eee8] transition hover:border-[#f97316]/60 hover:text-white">
              Back to Orange
            </Link>
          </div>
        </header>

        <section className="flex flex-1 items-center py-14 sm:py-20">
          <div className="w-full">
            <div className="max-w-4xl">
              <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#f9a66b]">
                Remote MCP setup
              </p>
              <h1 className="mt-4 text-balance text-5xl font-semibold leading-[1.02] sm:text-7xl">
                Give your agent memory in about a minute.
              </h1>
              <p className="mt-6 max-w-3xl text-pretty text-lg leading-8 text-[#b9c6bd] sm:text-xl">
                Connect the agent you already use to Orange. One browser sign-in gives it private recall, durable checkpoints, and end-of-session memory—without copying API keys.
              </p>
              <div className="mt-7 flex flex-wrap gap-2 font-mono text-xs text-[#cbd8cf]">
                {["Grok CLI", "Claude", "ChatGPT", "Streamable HTTP", "Supabase OAuth"].map((item) => (
                  <span key={item} className="rounded-full border border-white/10 bg-white/[0.04] px-3 py-1.5">{item}</span>
                ))}
              </div>
            </div>
            <div className="mt-12">
              <McpConnectCard />
            </div>
          </div>
        </section>

        <footer className="flex flex-col gap-2 border-t border-white/10 py-6 text-xs text-[#78867d] sm:flex-row sm:items-center sm:justify-between">
          <p>Orange uses your verified account to keep private memory isolated.</p>
          <p className="font-mono">https://orange-api-x38s.onrender.com/mcp</p>
        </footer>
      </div>
    </main>
  );
}
