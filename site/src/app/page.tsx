import Image from "next/image";
import type { CSSProperties, ReactNode } from "react";
import GrainCanvas from "@/components/grain-canvas";
import MemoryGraph from "@/components/memory-graph";
import TestChat from "@/components/test-chat";

const heroWords = "Orange remembers how the work was solved.".split(" ");

const schemaCode = `SessionIngestionRequest {
  source: "cursor"
  user_id: "dev_123"
  session_id: "debug-cors-042"
  participants: ["developer", "agent"]
  messages: [
    { role: "user", content: "CORS preflight returns 405" },
    { role: "assistant", content: "Try middleware order first" }
  ]
}

ping_context("same OPTIONS failure")
  -> vector match: problem_cors_order
  -> graph hydrate: failed path + worked fix + server.py`;

const appConnections = [
  {
    name: "Slack",
    mark: "S",
    position: "left-[7%] top-[16%]",
    color: "#78d6a3",
    prompt: "What did we decide with Rohan two weeks back about GTM in Spain?",
    body: "Orange links messy channel decisions into retrievable company memory, scoped to the right org.",
  },
  {
    name: "Google Meet",
    mark: "GM",
    position: "left-[37%] top-[5%]",
    color: "#8fb8ff",
    prompt: "Summarize the launch risk Rohan raised in last Friday's standup.",
    body: "Meet notes become facts, decisions, and follow-ups instead of disappearing after the call.",
  },
  {
    name: "Cursor",
    mark: "C",
    position: "right-[8%] top-[17%]",
    color: "#ffb36b",
    prompt: "Have we seen this OPTIONS failure before in this repo?",
    body: "Cursor sessions write private engineering memory only when the work ends and there is something durable.",
  },
  {
    name: "Claude Code",
    mark: "CC",
    position: "left-[15%] bottom-[16%]",
    color: "#f7c7ff",
    prompt: "Which prior refactor changed how auth middleware is ordered?",
    body: "Agent runs become searchable insight trails: what was tried, what stuck, and what to avoid.",
  },
  {
    name: "GitHub",
    mark: "GH",
    position: "right-[16%] bottom-[17%]",
    color: "#d7e1d8",
    prompt: "Why did we reject this PR pattern last month?",
    body: "Pull requests can connect implementation choices to the discussions and sessions that shaped them.",
  },
  {
    name: "Gmail",
    mark: "G",
    position: "left-[43%] bottom-[5%]",
    color: "#ffd166",
    prompt: "What did the customer ask us to change in the onboarding flow?",
    body: "Important customer context can become scoped memory without leaking private user identity.",
  },
  {
    name: "Linear",
    mark: "L",
    position: "left-[3%] top-[49%]",
    color: "#a8a4ff",
    prompt: "Which issue captured the decision to defer Spain GTM?",
    body: "Tickets can hydrate the why behind a product or engineering decision.",
  },
  {
    name: "Notion",
    mark: "N",
    position: "right-[3%] top-[49%]",
    color: "#f8f5ec",
    prompt: "Where did the team document our Markdown memory policy?",
    body: "Docs become structured company facts that coworkers can retrieve later.",
  },
  {
    name: "MCP",
    mark: "M",
    position: "left-[48%] top-[35%]",
    color: "#62d49c",
    prompt: "Before answering, ask Orange what this agent already knows.",
    body: "MCP lets coding agents call ping_context and store_session directly from their workflow.",
  },
];

const contextBlocks = [
  {
    title: "Before another engineer repeats a failed fix",
    body: "Orange can surface the old reasoning, what failed, and the decision that finally stuck.",
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

const integrations = ["Slack", "Google Meet", "Cursor", "Claude Code", "GitHub", "Gmail", "Linear", "Notion", "MCP"];

function RevealHeading({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2 className={className}>
      <span className="line-mask">
        <span data-line-reveal>{children}</span>
      </span>
    </h2>
  );
}

function SectionEyebrow({ children, tone = "orange" }: { children: ReactNode; tone?: "orange" | "green" }) {
  return (
    <p className={`font-mono text-sm font-semibold uppercase ${tone === "orange" ? "text-[#ff9f5f]" : "text-[#62d49c]"}`}>
      {children}
    </p>
  );
}

export default function Home() {
  return (
    <main className="min-h-screen overflow-x-clip bg-[#0d1210] text-[#f7f3e8]">
      <header className="site-nav fixed inset-x-0 top-0 z-40">
        <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <a className="font-mono text-sm font-semibold text-[#f7f3e8]" href="#top">
            ORANGE
          </a>
          <div className="hidden items-center gap-7 text-sm text-[#b8c3ba] md:flex">
            <a className="transition hover:text-[#ff9f5f]" href="#story">
              Flow
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#nodes">
              Apps
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#graph">
              Graph
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#try">
              Try
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#mcp">
              MCP
            </a>
          </div>
          <a className="shimmer-button inline-flex h-10 items-center justify-center rounded-md bg-[#f26d21] px-4 text-sm font-bold text-white shadow-[0_14px_36px_rgba(242,109,33,0.28)] transition hover:scale-[1.02]" href="#try">
            Try demo
          </a>
        </nav>
      </header>

      <section id="top" className="hero-section relative overflow-hidden pt-16">
        <div className="absolute inset-0">
          <Image
            src="/orange-hero.png"
            alt="Orange product texture"
            fill
            priority
            sizes="100vw"
            className="object-cover opacity-24"
          />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_78%_24%,rgba(255,139,61,0.28),transparent_34%),linear-gradient(115deg,#0d1210_0%,rgba(13,18,16,0.96)_40%,rgba(25,34,29,0.82)_100%)]" />
          <div data-hero-glow className="absolute right-[10%] top-[18%] h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle,rgba(255,138,48,0.32),rgba(255,188,91,0.12)_42%,transparent_70%)] blur-3xl" />
          <GrainCanvas />
        </div>

        <div className="relative z-[2] mx-auto grid min-h-[92svh] max-w-7xl gap-10 px-5 py-14 sm:px-8 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
          <div className="max-w-3xl">
            <p data-reveal className="mb-5 font-mono text-sm font-semibold uppercase text-[#ff9f5f]">
              Memory fabric for agentic engineering
            </p>
            <h1 className="text-balance text-5xl font-semibold leading-[0.98] text-[#fff9ef] sm:text-7xl lg:text-8xl">
              {heroWords.map((word) => (
                <span className="hero-word-mask" key={word}>
                  <span data-hero-word>{word}</span>{" "}
                </span>
              ))}
            </h1>
            <p data-reveal className="mt-6 max-w-2xl text-pretty text-lg leading-8 text-[#c7d0c9] sm:text-xl">
              Capture developer sessions from Claude Code, Cursor, Slack, Meet, and MCP. Extract durable insights, company facts, private steering, files, and metadata that future agents need before they start repeating work.
            </p>
            <div data-reveal className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a className="hero-cta-watch shimmer-button inline-flex h-12 items-center justify-center rounded-md bg-[#f26d21] px-6 text-sm font-bold text-white shadow-[0_18px_46px_rgba(242,109,33,0.28)] transition hover:scale-[1.02]" href="#story">
                Watch the flow
              </a>
              <a className="inline-flex h-12 items-center justify-center rounded-md border border-white/20 px-6 text-sm font-bold text-[#fff9ef] transition hover:scale-[1.02] hover:border-[#ff9f5f] hover:text-[#ffb777]" href="#graph">
                Open graph
              </a>
            </div>
            <p className="orange-tagline">
              This is what Orange does —<br />
              bring light to the collective intelligence of your team.
            </p>
          </div>

          <div className="relative min-h-[560px]">
            <div className="absolute inset-0 rounded-[2rem] border border-white/10 bg-[#17221c]/78 shadow-[0_34px_120px_rgba(0,0,0,0.42)] backdrop-blur-xl" />
            <div data-ping-card className="absolute inset-x-4 top-6 rounded-xl border border-white/12 bg-[#080d0a]/92 p-5 text-white shadow-2xl backdrop-blur sm:inset-x-8">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <p className="font-mono text-xs uppercase text-[#ffb36b]">ping_context</p>
                  <p className="mt-1 text-sm text-[#d7e1d8]">similar issue detected</p>
                </div>
                <span className="rounded-md bg-[#ffb36b] px-2.5 py-1 font-mono text-xs font-semibold text-[#1b201c]" data-score-target="0.91">
                  0.91
                </span>
              </div>

              <div className="mt-5 grid gap-3">
                <div data-ping-line className="rounded-md border border-[#ffb36b]/30 bg-[#ffb36b]/10 p-4">
                  <p className="font-mono text-xs uppercase text-[#ffb36b]">Insight</p>
                  <p className="mt-2 text-lg font-semibold">FastAPI CORS middleware order</p>
                  <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                    Preflight failed because middleware was registered after route setup.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div data-ping-line className="rounded-md border border-white/10 bg-white/[0.06] p-4">
                    <p className="font-mono text-xs text-[#ffd166]">failed path</p>
                    <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                      Changing allowed origins did not fix OPTIONS.
                    </p>
                  </div>
                  <div data-ping-line className="rounded-md border border-white/10 bg-white/[0.06] p-4">
                    <p className="font-mono text-xs text-[#62d49c]">worked fix</p>
                    <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                      Move CORSMiddleware before include_router.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="absolute bottom-8 left-5 right-5 grid grid-cols-3 gap-3 sm:left-12">
              {["vector hit", "graph hydrate", "context block"].map((label, index) => (
                <div data-hero-metric className="rounded-md border border-white/12 bg-white/88 p-4 text-[#17221c] shadow-[0_18px_42px_rgba(0,0,0,0.18)] backdrop-blur" key={label}>
                  <p className="font-mono text-xs text-[#c5551c]">0{index + 1}</p>
                  <p className="mt-3 text-sm font-semibold">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
        <div className="hero-darkness" aria-hidden="true" />
      </section>

      <section className="border-y border-white/10 bg-[#101713]">
        <div className="mx-auto grid max-w-7xl gap-6 px-5 py-10 sm:px-8 lg:grid-cols-[1.2fr_1fr] lg:items-center">
          <p className="text-2xl font-semibold leading-tight text-[#fff9ef]">
            Recognized as a top-5 infra team project at South Park Commons.
          </p>
          <div className="flex flex-wrap gap-2 lg:justify-end" aria-label="Orange ecosystem integrations">
            {integrations.map((item) => (
              <span className="rounded-md border border-white/12 bg-white/[0.06] px-3 py-2 font-mono text-xs font-semibold text-[#d7e1d8]" key={item}>
                {item}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="story" data-scroll-story className="relative bg-[#f8f5ec] text-[#161b18]">
        <div className="mx-auto grid min-h-screen max-w-7xl gap-10 px-5 py-16 sm:px-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-center lg:py-0">
          <div className="lg:sticky lg:top-28">
            <SectionEyebrow>Capture → Extract → Retrieve</SectionEyebrow>
            <RevealHeading className="mt-4 text-4xl font-semibold leading-tight sm:text-6xl">
              The memory loop becomes visible as you scroll.
            </RevealHeading>
            <div className="mt-8 grid gap-3">
              {["SessionIngestionRequest", "Triage + Insight agents", "ping_context response"].map((label, index) => (
                <div className="pipeline-step rounded-lg border border-[#24352d]/12 bg-white p-4 shadow-sm" key={label}>
                  <p className="font-mono text-xs text-[#c5551c]">0{index + 1}</p>
                  <p className="mt-2 text-lg font-semibold text-[#24352d]">{label}</p>
                </div>
              ))}
            </div>
          </div>

          <div data-story-viewport className="overflow-hidden">
            <div data-story-track className="flex flex-col gap-5 lg:w-max lg:flex-row">
              <article className="story-panel">
                <p className="font-mono text-xs font-semibold uppercase text-[#c5551c]">Capture</p>
                <h3 className="mt-4 text-3xl font-semibold">A session comes in from Cursor or Claude Code.</h3>
                <div className="mt-8 rounded-lg bg-[#111812] p-5 font-mono text-sm leading-7 text-[#dce8df]">
                  {["Turn 1 [user]: CORS preflight returns 405", "Turn 2 [assistant]: Reproduce OPTIONS locally", "Turn 3 [user]: Origin list change failed"].map((line) => (
                    <p className="type-line" data-story-type key={line}>{line}</p>
                  ))}
                </div>
              </article>

              <article className="story-panel">
                <p className="font-mono text-xs font-semibold uppercase text-[#c5551c]">Extract</p>
                <h3 className="mt-4 text-3xl font-semibold">Agents extract durable insights, facts, and steering.</h3>
                <div className="mini-graph mt-8">
                  {["Insight", "User fact", "Company fact", "Steering"].map((node, index) => (
                    <span style={{ animationDelay: `${index * 180}ms` }} key={node}>{node}</span>
                  ))}
                </div>
              </article>

              <article className="story-panel">
                <p className="font-mono text-xs font-semibold uppercase text-[#c5551c]">Retrieve</p>
                <h3 className="mt-4 text-3xl font-semibold">The next agent receives the neighborhood, not a vague memory.</h3>
                <div className="mt-8 rounded-lg border border-[#24352d]/10 bg-white p-5 shadow-sm">
                  <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-sm leading-7 text-[#24352d]">{`{
  "matched_nodes": ["Insight", "Company fact"],
  "similarity_score": 0.91,
  "neighborhood": ["decision", "source", "server.py"]
}`}</pre>
                </div>
              </article>
            </div>
          </div>
        </div>
      </section>

      <section id="nodes" className="bg-[#0d1210] px-5 py-16 text-[#fff9ef] sm:px-8 lg:py-24">
        <div className="mx-auto max-w-7xl">
          <div className="grid gap-10 lg:grid-cols-[0.82fr_1.18fr] lg:items-end">
            <div>
              <SectionEyebrow tone="green">Connected sources</SectionEyebrow>
              <RevealHeading className="mt-4 text-4xl font-semibold leading-tight sm:text-6xl">
                One memory fabric across the apps where work happens.
              </RevealHeading>
            </div>
            <p data-reveal className="max-w-2xl text-lg leading-8 text-[#c7d0c9]">
              Orange sits in the middle of conversations, code sessions, meetings, docs, tickets, and email. Hover an app to see the kind of question it can answer later.
            </p>
          </div>

          <div className="mt-12 grid gap-5 lg:grid-cols-[1.1fr_0.9fr] lg:items-stretch">
            <div data-bento-grid className="source-map-card relative min-h-[620px] overflow-hidden rounded-xl border border-white/10 bg-[#121a16] p-4 shadow-[0_30px_90px_rgba(0,0,0,0.28)] sm:p-6">
              <div className="absolute inset-0 bg-[radial-gradient(circle_at_50%_45%,rgba(242,109,33,0.2),transparent_32%),radial-gradient(circle_at_18%_20%,rgba(98,212,156,0.12),transparent_25%),radial-gradient(circle_at_82%_24%,rgba(143,184,255,0.12),transparent_24%)]" />
              <svg className="source-map-lines absolute inset-0 h-full w-full" role="presentation" viewBox="0 0 100 100" preserveAspectRatio="none">
                {[
                  [50, 46, 14, 21],
                  [50, 46, 43, 10],
                  [50, 46, 84, 22],
                  [50, 46, 22, 81],
                  [50, 46, 78, 80],
                  [50, 46, 49, 91],
                  [50, 46, 9, 53],
                  [50, 46, 91, 53],
                  [50, 46, 53, 43],
                ].map(([x1, y1, x2, y2], index) => (
                  <line key={`${x2}-${y2}`} x1={x1} y1={y1} x2={x2} y2={y2} style={{ animationDelay: `${index * 90}ms` }} />
                ))}
              </svg>

              <div className="orange-core-logo absolute left-1/2 top-[46%] z-10 -translate-x-1/2 -translate-y-1/2">
                <span className="orange-core-leaf" />
                <span className="orange-core-ring">O</span>
                <strong>ORANGE</strong>
                <small>memory fabric</small>
              </div>

              {appConnections.map((app) => (
                <button
                  className={`source-node group absolute z-20 ${app.position}`}
                  key={app.name}
                  type="button"
                  style={{ "--source-color": app.color } as CSSProperties}
                  aria-label={`${app.name}: ${app.prompt}`}
                >
                  <span className="source-mark">{app.mark}</span>
                  <span className="source-name">{app.name}</span>
                  <span className="source-tooltip" role="tooltip">
                    <strong>{app.prompt}</strong>
                    <span>{app.body}</span>
                  </span>
                </button>
              ))}

              <div className="absolute bottom-5 left-5 right-5 z-10 flex flex-wrap gap-2">
                {["private user facts", "company facts", "agent sessions", "meetings", "tickets", "email"].map((label) => (
                  <span className="rounded-md border border-white/10 bg-white/[0.06] px-3 py-2 font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#c7d0c9]" key={label}>
                    {label}
                  </span>
                ))}
              </div>
            </div>

            <div className="rounded-xl border border-white/10 bg-[#17221c] p-5 shadow-[0_30px_90px_rgba(0,0,0,0.28)]">
              <div className="mb-4 flex items-center justify-between border-b border-white/10 pb-4">
                <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-[#ffb36b]">live contract</p>
                <span className="rounded-full border border-white/12 bg-white/[0.06] px-2.5 py-1 font-mono text-xs text-[#d7e1d8]">typing</span>
              </div>
              <pre className="overflow-x-auto whitespace-pre-wrap font-mono text-sm leading-7 text-[#dce8df]">
                <code data-type-code>{schemaCode}</code>
              </pre>
            </div>
          </div>
        </div>
      </section>

      <section id="graph" className="border-y border-[#24352d]/10 bg-[#eef3ed] text-[#161b18]">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <div className="mb-10 grid gap-6 lg:grid-cols-[1fr_auto] lg:items-end">
            <div className="max-w-3xl">
              <div className="flex items-center gap-3">
                <SectionEyebrow>Interactive graph</SectionEyebrow>
                <span className="live-badge"><span /> Live</span>
              </div>
              <RevealHeading className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
                Drag through a memory neighborhood.
              </RevealHeading>
              <p data-reveal className="mt-5 text-lg leading-8 text-[#536057]">
                Each node is a durable unit of developer memory. Move nodes to inspect relationships, then click any node to see what Orange can return to an agent.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg bg-white p-4 shadow-sm">
                <p className="text-3xl font-semibold text-[#c5551c]" data-count-to="2">0</p>
                <p className="mt-1 text-xs font-semibold text-[#536057]">scope views</p>
              </div>
              <div className="rounded-lg bg-white p-4 shadow-sm">
                <p className="text-3xl font-semibold text-[#2f6f5e]" data-count-to="91" data-count-suffix="%">0%</p>
                <p className="mt-1 text-xs font-semibold text-[#536057]">match score</p>
              </div>
              <div className="rounded-lg bg-white p-4 shadow-sm">
                <p className="text-3xl font-semibold text-[#24352d]" data-count-to="3">0</p>
                <p className="mt-1 text-xs font-semibold text-[#536057]">stores</p>
              </div>
            </div>
          </div>
          <MemoryGraph />
        </div>
      </section>

      <section id="try" className="bg-white text-[#161b18]">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <div className="mb-10 max-w-3xl">
            <SectionEyebrow tone="green">Test memory capture</SectionEyebrow>
            <RevealHeading className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
              Chat first. Store only when the session is done.
            </RevealHeading>
            <p data-reveal className="mt-5 text-lg leading-8 text-[#536057]">
              Add a profile, talk to the OpenAI-backed demo agent, then mark the conversation done to watch Orange add the session into the shared graph.
            </p>
          </div>
          <TestChat />
        </div>
      </section>

      <section id="mcp" className="bg-[#1a221d] text-white">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <SectionEyebrow>Agent-triggered retrieval</SectionEyebrow>
          <RevealHeading className="mt-4 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
            The agent asks Orange when the current session is missing history.
          </RevealHeading>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {contextBlocks.map((item) => (
              <article data-reveal className="rounded-lg border border-white/10 bg-white/[0.06] p-6" key={item.title}>
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
