import Link from "next/link";

import McpConnectCard from "@/components/mcp-connect-card";

export const metadata = {
  title: "Connect Orange",
  description:
    "Connect Grok, Claude, ChatGPT, or any MCP client to Orange with one URL and browser sign-in. No tokens to copy.",
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
            <p className="font-mono text-sm font-semibold uppercase text-[#f9a66b]">
              Connect Orange · Remote MCP
            </p>
            <h1 className="mt-4 max-w-3xl text-5xl font-semibold leading-tight sm:text-6xl">
              One URL. One browser login. Every MCP client.
            </h1>
            <p className="mt-5 max-w-2xl text-lg leading-8 text-[#cbd8cf]">
              Orange keeps a single Streamable HTTP endpoint for Grok CLI, Claude Code / Claude.ai,
              ChatGPT, and generic MCP clients. Sign in in the browser—no bearer tokens or environment
              secrets to manage.
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
