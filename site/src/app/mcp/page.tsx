import Link from "next/link";

import McpConnectCard from "@/components/mcp-connect-card";

export const metadata = {
  title: "Connect Orange MCP",
  description: "Generate a desktop MCP setup for Codex or Claude Code.",
};

export default function McpPage() {
  return (
    <main className="min-h-screen bg-[#0d1210] text-white">
      <div className="mx-auto flex min-h-screen max-w-5xl flex-col px-5 py-8 sm:px-8">
        <header className="flex items-center justify-between">
          <Link href="/" className="font-mono text-sm font-semibold">
            ORANGE
          </Link>
          <Link href="/" className="text-sm text-[#b8c3ba] transition hover:text-[#f97316]">
            Back to demo
          </Link>
        </header>

        <section className="flex flex-1 items-center py-16">
          <div className="w-full">
            <p className="font-mono text-sm font-semibold uppercase text-[#f9a66b]">Desktop MCP setup</p>
            <h1 className="mt-4 max-w-3xl text-5xl font-semibold leading-tight sm:text-6xl">
              Connect Orange to Codex in under a minute.
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-[#cbd8cf]">
              Generate a personal MCP token, paste the config into Codex, and Orange will remember completed agent sessions under your email.
            </p>
            <div className="mt-10">
              <McpConnectCard />
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
