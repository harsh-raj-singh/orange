import Image from "next/image";
import MemoryGraph from "@/components/memory-graph";
import TestChat from "@/components/test-chat";

const pipeline = [
  {
    step: "Normalize",
    detail: "Claude Code, Cursor, MCP, CI agents, or local tools send one session shape.",
  },
  {
    step: "Extract",
    detail: "Orange builds typed problem, solution, attempt, artifact, and concept nodes.",
  },
  {
    step: "Retrieve",
    detail: "Agents call Orange only when they need prior context, then receive the graph neighborhood.",
  },
];

const nodeTypes = [
  "Problem",
  "Solution",
  "Attempt",
  "Artifact",
  "Concept",
  "Session",
];

const contextBlocks = [
  {
    title: "Before another engineer repeats a failed fix",
    body: "Orange can surface the old attempt, why it failed, and the solution that finally worked.",
  },
  {
    title: "When a new agent joins a codebase cold",
    body: "It gets compact context first, then can expand into exact graph-backed session history.",
  },
  {
    title: "When the same bug returns in a new form",
    body: "Vector search finds the semantic match; Neo4j brings back causes, fixes, files, and follow-ups.",
  },
];

export default function Home() {
  return (
    <main className="min-h-screen bg-[#f7f3e8] text-[#161b18]">
      <header className="fixed inset-x-0 top-0 z-40 border-b border-[#24352d]/10 bg-[#f7f3e8]/86 backdrop-blur-xl">
        <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <a className="font-mono text-sm font-semibold tracking-[0.2em] text-[#24352d]" href="#top">
            ORANGE
          </a>
          <div className="hidden items-center gap-7 text-sm text-[#536057] md:flex">
            <a className="transition hover:text-[#c5551c]" href="#fabric">
              Fabric
            </a>
            <a className="transition hover:text-[#c5551c]" href="#nodes">
              Nodes
            </a>
            <a className="transition hover:text-[#c5551c]" href="#graph">
              Graph
            </a>
            <a className="transition hover:text-[#c5551c]" href="#try">
              Try
            </a>
            <a className="transition hover:text-[#c5551c]" href="#mcp">
              MCP
            </a>
          </div>
          <a
            className="inline-flex h-10 items-center justify-center rounded-md bg-[#24352d] px-4 text-sm font-semibold text-white shadow-[0_14px_36px_rgba(36,53,45,0.16)] transition hover:bg-[#c5551c]"
            href="#mcp"
          >
            See flow
          </a>
        </nav>
      </header>

      <section id="top" className="relative overflow-hidden pt-16">
        <div className="absolute inset-0">
          <Image
            src="/orange-hero.png"
            alt="Orange brand texture"
            fill
            priority
            sizes="100vw"
            className="object-cover opacity-16"
          />
          <div className="absolute inset-0 bg-[linear-gradient(110deg,#f7f3e8_0%,rgba(247,243,232,0.92)_44%,rgba(247,243,232,0.72)_100%)]" />
        </div>

        <div className="relative mx-auto grid min-h-[92svh] max-w-7xl gap-10 px-5 py-14 sm:px-8 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
          <div className="max-w-3xl">
            <p className="mb-5 font-mono text-sm font-semibold uppercase tracking-[0.28em] text-[#c5551c]">
              Memory fabric for agentic engineering
            </p>
            <h1 className="text-balance text-5xl font-semibold leading-[0.98] text-[#161b18] sm:text-7xl lg:text-8xl">
              Orange remembers how the work was solved.
            </h1>
            <p className="mt-6 max-w-2xl text-pretty text-lg leading-8 text-[#48534d] sm:text-xl">
              Capture developer sessions from Claude Code, Cursor, and other agents. Turn them into graph-backed memory so the next teammate or agent learns from what already happened.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a
                className="inline-flex h-12 items-center justify-center rounded-md bg-[#c5551c] px-6 text-sm font-bold text-white shadow-[0_18px_46px_rgba(197,85,28,0.22)] transition hover:bg-[#9f4218]"
                href="#fabric"
              >
                Explore architecture
              </a>
              <a
                className="inline-flex h-12 items-center justify-center rounded-md border border-[#24352d]/25 px-6 text-sm font-bold text-[#24352d] transition hover:border-[#c5551c] hover:text-[#c5551c]"
                href="#try"
              >
                Try chat
              </a>
            </div>
          </div>

          <div className="relative min-h-[540px]">
            <div className="absolute inset-0 rounded-[2rem] bg-[#24352d] shadow-[0_34px_100px_rgba(36,53,45,0.24)]" />
            <div className="absolute inset-x-5 top-6 rounded-lg border border-white/12 bg-[#101512]/92 p-5 text-white shadow-2xl backdrop-blur">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <p className="font-mono text-xs uppercase tracking-[0.22em] text-[#ffb36b]">
                    ping_context
                  </p>
                  <p className="mt-1 text-sm text-[#d7e1d8]">similar issue detected</p>
                </div>
                <span className="rounded-md bg-[#ffb36b] px-2.5 py-1 font-mono text-xs font-semibold text-[#1b201c]">
                  0.91
                </span>
              </div>

              <div className="mt-5 grid gap-3">
                <div className="rounded-md border border-[#ffb36b]/30 bg-[#ffb36b]/10 p-4">
                  <p className="font-mono text-xs uppercase tracking-[0.18em] text-[#ffb36b]">
                    Problem
                  </p>
                  <p className="mt-2 text-lg font-semibold">
                    FastAPI CORS middleware order
                  </p>
                  <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                    Preflight failed because middleware was registered after route setup.
                  </p>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div className="rounded-md border border-white/10 bg-white/[0.06] p-4">
                    <p className="font-mono text-xs text-[#8fb1a0]">failed path</p>
                    <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                      Changing allowed origins did not fix OPTIONS.
                    </p>
                  </div>
                  <div className="rounded-md border border-white/10 bg-white/[0.06] p-4">
                    <p className="font-mono text-xs text-[#8fb1a0]">worked fix</p>
                    <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                      Move CORSMiddleware before include_router.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="absolute bottom-8 left-10 right-0 grid grid-cols-3 gap-3">
              {["vector hit", "graph hydrate", "context block"].map((label, index) => (
                <div
                  className="rounded-md border border-[#24352d]/10 bg-white/86 p-4 shadow-[0_18px_42px_rgba(36,53,45,0.14)] backdrop-blur"
                  key={label}
                >
                  <p className="font-mono text-xs text-[#c5551c]">0{index + 1}</p>
                  <p className="mt-3 text-sm font-semibold text-[#24352d]">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="fabric" className="border-y border-[#24352d]/10 bg-[#ffffff]">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <p className="font-mono text-sm font-semibold uppercase tracking-[0.25em] text-[#c5551c]">
                Canonical path
              </p>
              <h2 className="mt-4 text-4xl font-semibold leading-tight text-[#161b18] sm:text-5xl">
                One ingestion contract from every developer tool.
              </h2>
            </div>
            <div className="grid gap-4 md:grid-cols-3">
              {pipeline.map((item, index) => (
                <article className="rounded-lg border border-[#d8ded7] bg-[#f7f3e8] p-6" key={item.step}>
                  <p className="font-mono text-sm text-[#c5551c]">0{index + 1}</p>
                  <h3 className="mt-5 text-xl font-semibold text-[#161b18]">{item.step}</h3>
                  <p className="mt-3 text-sm leading-6 text-[#536057]">{item.detail}</p>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="nodes" className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
        <div className="grid gap-12 lg:grid-cols-[1fr_1fr] lg:items-center">
          <div>
            <p className="font-mono text-sm font-semibold uppercase tracking-[0.25em] text-[#2f6f5e]">
              Node creation
            </p>
            <h2 className="mt-4 text-4xl font-semibold leading-tight text-[#161b18] sm:text-5xl">
              Compact for search. Rich when the graph is opened.
            </h2>
            <p className="mt-5 text-lg leading-8 text-[#536057]">
              Orange stores searchable summaries in Chroma and hydrates the exact Neo4j node neighborhood when a session needs context.
            </p>
            <div className="mt-8 flex flex-wrap gap-3">
              {nodeTypes.map((type) => (
                <span className="rounded-md border border-[#24352d]/15 bg-white px-3 py-2 font-mono text-sm text-[#24352d]" key={type}>
                  {type}
                </span>
              ))}
            </div>
          </div>
          <div className="rounded-lg border border-[#24352d]/10 bg-[#24352d] p-5 text-white shadow-[0_28px_80px_rgba(36,53,45,0.22)]">
            <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-sm leading-7 text-[#dce8df]">
{`SessionIngestionRequest
  source: "cursor" | "claude" | "mcp"
  user_id: "dev_123"
  started_at: "2026-05-15T09:10:00Z"
  participants: ["dev_123", "assistant"]
  transcript: "Turn 1 [user]: ..."

retrieval:
  vector -> neo4j_node_id -> neighborhood`}
            </pre>
          </div>
        </div>
      </section>

      <section id="graph" className="border-y border-[#24352d]/10 bg-[#eef3ed]">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <div className="mb-10 max-w-3xl">
            <p className="font-mono text-sm font-semibold uppercase tracking-[0.25em] text-[#c5551c]">
              Interactive graph
            </p>
            <h2 className="mt-4 text-4xl font-semibold leading-tight text-[#161b18] sm:text-5xl">
              Drag through a memory neighborhood.
            </h2>
            <p className="mt-5 text-lg leading-8 text-[#536057]">
              Each node represents a durable unit of developer memory. Move nodes to inspect relationships, then click any node to see what Orange can return to an agent.
            </p>
          </div>
          <MemoryGraph />
        </div>
      </section>

      <section id="try" className="bg-white">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <div className="mb-10 max-w-3xl">
            <p className="font-mono text-sm font-semibold uppercase tracking-[0.25em] text-[#2f6f5e]">
              Test memory capture
            </p>
            <h2 className="mt-4 text-4xl font-semibold leading-tight text-[#161b18] sm:text-5xl">
              Chat first. Store only when the session is done.
            </h2>
            <p className="mt-5 text-lg leading-8 text-[#536057]">
              Add a profile, talk to the NVIDIA-backed demo agent, then mark the conversation done to watch Orange add the session into the shared graph.
            </p>
          </div>
          <TestChat />
        </div>
      </section>

      <section id="mcp" className="bg-[#1a221d] text-white">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <p className="font-mono text-sm font-semibold uppercase tracking-[0.25em] text-[#ffb36b]">
            Agent-triggered retrieval
          </p>
          <h2 className="mt-4 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
            The agent asks Orange when it feels the current session is missing history.
          </h2>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {contextBlocks.map((item) => (
              <article className="rounded-lg border border-white/10 bg-white/[0.06] p-6" key={item.title}>
                <h3 className="text-xl font-semibold">{item.title}</h3>
                <p className="mt-3 text-sm leading-6 text-[#d6e1d8]">{item.body}</p>
              </article>
            ))}
          </div>
        </div>
      </section>
    </main>
  );
}
