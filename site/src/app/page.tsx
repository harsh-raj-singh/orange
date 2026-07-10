import Image from "next/image";
import { siClaude, siCursor } from "simple-icons";
import type { CSSProperties, ReactNode } from "react";
import GrainCanvas from "@/components/grain-canvas";
import MemoryGraph from "@/components/memory-graph";
import TestChat from "@/components/test-chat";
import { getVerifiedSupabaseSession } from "@/lib/supabase-server";

const heroWords = "Your next agent should know what the last one learned.".split(" ");

const schemaCode = `complete_conversation({
  source: "claude-code",
  session_id: "debug-cors-042",
  transcript: "...",
  worth_storing: true
})

recall_memory({
  query: "OPTIONS still returns 405"
})

→ matched insight: CORS middleware order
→ includes: failed attempt, working fix, server.py
→ scoped to the signed-in user`;

const appConnections = [
  {
    name: "Slack",
    icon: "slack",
    position: "left-[22%] top-[35%]",
    color: "#4A154B",
    path: "M 25 40 C 32 42 40 46 50 48",
    time: "team decision",
    prompt: "What did we decide about the Spain launch?",
    body: "Orange returns the decision, its source, and the people involved.",
  },
  {
    name: "Grok CLI",
    icon: "terminal",
    position: "right-[21%] top-[31%]",
    color: "#F4F1E8",
    path: "M 72 36 C 66 40 58 45 50 48",
    time: "remote MCP",
    prompt: "Have we solved this deployment failure before?",
    body: "Orange recalls the previous root cause before Grok starts over.",
  },
  {
    name: "Claude Code",
    icon: "claude",
    position: "left-[27%] bottom-[18%]",
    color: "#D97706",
    path: "M 31 74 C 36 64 43 54 50 48",
    time: "coding session",
    prompt: "Why did OPTIONS fail on /api/ingest?",
    body: "The fix and the failed origin-list attempt are both preserved.",
  },
  {
    name: "ChatGPT",
    icon: "openai",
    position: "right-[25%] bottom-[23%]",
    color: "#74AA9C",
    path: "M 72 70 C 65 61 57 53 50 48",
    time: "developer-mode app",
    prompt: "Continue from the last architecture decision.",
    body: "The same private memory is available through the shared MCP endpoint.",
  },
];

const contextBlocks = [
  {
    title: "Recall before work begins",
    body: "The agent asks Orange for relevant history and receives the closest insight plus its connected evidence.",
  },
  {
    title: "Checkpoint the important turn",
    body: "A decision or root cause can be saved mid-session, before a crash or context limit makes it disappear.",
  },
  {
    title: "Complete the useful session",
    body: "When the work ends, Orange extracts only durable information and updates the graph for the next client.",
  },
];

const integrations = [
  { name: "Slack", icon: "slack" },
  { name: "Grok CLI", icon: "terminal" },
  { name: "Cursor", icon: "cursor" },
  { name: "Claude Code", icon: "claude" },
  { name: "ChatGPT", icon: "openai" },
  { name: "Codex", icon: "openai" },
  { name: "Any MCP client", icon: "mcp" },
];

const integrationGroupStyle: CSSProperties = {
  minWidth: "max(96rem, 100vw)",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "1rem",
  paddingRight: "1rem",
};

const integrationChipStyle: CSSProperties = {
  display: "inline-flex",
  minWidth: "10.5rem",
  alignItems: "center",
  justifyContent: "center",
  gap: "0.8rem",
  border: "1px solid rgba(255, 255, 255, 0.14)",
  borderRadius: "0.5rem",
  background: "rgba(255, 255, 255, 0.075)",
  padding: "0.95rem 1.25rem",
  color: "#dce8df",
  fontFamily: "var(--font-geist-mono), ui-monospace, monospace",
  fontSize: "0.95rem",
  fontWeight: 750,
  lineHeight: 1,
  whiteSpace: "nowrap",
  boxShadow: "inset 0 1px rgba(255, 255, 255, 0.08)",
};

const integrationIconStyle: CSSProperties = {
  width: "1.25rem",
  height: "1.25rem",
  color: "#ffb36b",
};

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

function BrandIcon({ icon, style }: { icon: string; style?: CSSProperties }) {
  if (icon === "slack") {
    return (
      <svg aria-hidden="true" viewBox="0 0 122.8 122.8" style={style}>
        <path d="M30.3 77.2c0 8.4-6.8 15.2-15.2 15.2S0 85.6 0 77.2 6.8 62 15.2 62h15.2v15.2z" fill="#E01E5A" />
        <path d="M37.9 77.2c0-8.4 6.8-15.2 15.2-15.2s15.2 6.8 15.2 15.2v38c0 8.4-6.8 15.2-15.2 15.2s-15.2-6.8-15.2-15.2v-38z" fill="#E01E5A" />
        <path d="M53.1 30.3c-8.4 0-15.2-6.8-15.2-15.2S44.7 0 53.1 0s15.2 6.8 15.2 15.2v15.2H53.1z" fill="#36C5F0" />
        <path d="M53.1 37.9c8.4 0 15.2 6.8 15.2 15.2S61.5 68.3 53.1 68.3h-38C6.8 68.3 0 61.5 0 53.1s6.8-15.2 15.2-15.2h37.9z" fill="#36C5F0" />
        <path d="M92.4 53.1c0-8.4 6.8-15.2 15.2-15.2s15.2 6.8 15.2 15.2-6.8 15.2-15.2 15.2H92.4V53.1z" fill="#2EB67D" />
        <path d="M84.8 53.1c0 8.4-6.8 15.2-15.2 15.2s-15.2-6.8-15.2-15.2v-38C54.4 6.8 61.2 0 69.6 0s15.2 6.8 15.2 15.2v37.9z" fill="#2EB67D" />
        <path d="M69.6 92.4c8.4 0 15.2 6.8 15.2 15.2s-6.8 15.2-15.2 15.2-15.2-6.8-15.2-15.2V92.4h15.2z" fill="#ECB22E" />
        <path d="M69.6 84.8c-8.4 0-15.2-6.8-15.2-15.2s6.8-15.2 15.2-15.2h38c8.4 0 15.2 6.8 15.2 15.2s-6.8 15.2-15.2 15.2h-38z" fill="#ECB22E" />
      </svg>
    );
  }

  if (icon === "terminal" || icon === "mcp" || icon === "openai") {
    return (
      <svg aria-hidden="true" viewBox="0 0 24 24" style={style} fill="none">
        {icon === "terminal" ? (
          <>
            <rect x="3" y="4" width="18" height="16" rx="3" stroke="currentColor" strokeWidth="1.8" />
            <path d="m7 9 3 3-3 3M12.5 15H17" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </>
        ) : icon === "openai" ? (
          <>
            <circle cx="12" cy="12" r="7.5" stroke="currentColor" strokeWidth="1.7" />
            <path d="M12 4.5v15M4.5 12h15M6.7 6.7l10.6 10.6M17.3 6.7 6.7 17.3" stroke="currentColor" strokeWidth="1.25" strokeLinecap="round" opacity=".75" />
          </>
        ) : (
          <>
            <circle cx="12" cy="12" r="3" stroke="currentColor" strokeWidth="1.8" />
            <circle cx="5" cy="7" r="2" stroke="currentColor" strokeWidth="1.8" />
            <circle cx="19" cy="7" r="2" stroke="currentColor" strokeWidth="1.8" />
            <circle cx="12" cy="20" r="2" stroke="currentColor" strokeWidth="1.8" />
            <path d="m6.8 8.2 2.9 2M17.2 8.2l-2.9 2M12 15v3" stroke="currentColor" strokeWidth="1.8" />
          </>
        )}
      </svg>
    );
  }

  const iconMap = {
    cursor: siCursor,
    claude: siClaude,
  } as const;
  const selectedIcon = iconMap[icon as keyof typeof iconMap];

  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" style={style}>
      <path d={selectedIcon.path} fill="currentColor" />
    </svg>
  );
}

function IntegrationStrip() {
  return (
    <div className="integration-marquee" aria-label="Orange ecosystem integrations">
      <div className="integration-marquee-track">
        {[0, 1, 2].map((groupIndex) => (
          <div className="integration-marquee-group" aria-hidden={groupIndex > 0} key={groupIndex} style={integrationGroupStyle}>
            {integrations.map((item) => (
              <span className="integration-chip" key={`${groupIndex}-${item.name}`} style={integrationChipStyle}>
                <span className="integration-chip-icon">
                  <BrandIcon icon={item.icon} style={integrationIconStyle} />
                </span>
                {item.name}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

export default async function Home() {
  const auth = await getVerifiedSupabaseSession();

  return (
    <main className="min-h-screen overflow-x-clip bg-[#0d1210] text-[#f7f3e8]">
      <header className="site-nav fixed inset-x-0 top-0 z-40">
        <nav className="mx-auto flex h-16 max-w-7xl items-center justify-between px-5 sm:px-8">
          <a className="font-mono text-sm font-semibold text-[#f7f3e8]" href="#top">
            ORANGE
          </a>
          <div className="hidden items-center gap-7 text-sm text-[#b8c3ba] md:flex">
            <a className="transition hover:text-[#ff9f5f]" href="#story">
              How it works
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#nodes">
              Sources
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#graph">
              Memory graph
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#try">
              Try it
            </a>
            <a className="transition hover:text-[#ff9f5f]" href="#mcp">
              MCP setup
            </a>
          </div>
          {auth ? (
            <div className="flex items-center gap-3">
              <span className="hidden max-w-48 truncate text-xs text-[#b8c3ba] sm:block">
                {auth.email}
              </span>
              <form action="/api/auth/sign-out" method="post">
                <button
                  type="submit"
                  className="inline-flex h-10 items-center justify-center rounded-md border border-white/20 px-4 text-sm font-bold text-white transition hover:border-[#ff9f5f] hover:text-[#ffb777]"
                >
                  Sign out
                </button>
              </form>
            </div>
          ) : (
            <a
              className="shimmer-button inline-flex h-10 items-center justify-center rounded-md bg-[#f26d21] px-4 text-sm font-bold text-white shadow-[0_14px_36px_rgba(242,109,33,0.28)] transition hover:scale-[1.02]"
              href="/login?next=%2F%23try"
            >
              Sign in
            </a>
          )}
        </nav>
      </header>

      <section id="top" className="hero-section relative overflow-hidden pt-16">
        <div className="absolute inset-0">
          <Image
            src="/orange-hero.png"
            alt="Orange product texture"
            fill
            priority
            sizes="(max-width: 768px) 100vw, (max-width: 1200px) 80vw, 60vw"
            quality={85}
            className="object-cover opacity-24"
          />
          <div className="absolute inset-0 bg-[radial-gradient(circle_at_78%_24%,rgba(255,139,61,0.28),transparent_34%),linear-gradient(115deg,#0d1210_0%,rgba(13,18,16,0.96)_40%,rgba(25,34,29,0.82)_100%)]" />
          <div data-hero-glow className="absolute right-[10%] top-[18%] h-[34rem] w-[34rem] rounded-full bg-[radial-gradient(circle,rgba(255,138,48,0.32),rgba(255,188,91,0.12)_42%,transparent_70%)] blur-3xl" />
          <GrainCanvas />
        </div>

        <div className="relative z-[2] mx-auto grid min-h-[92svh] max-w-7xl gap-10 px-5 py-14 sm:px-8 lg:grid-cols-[0.95fr_1.05fr] lg:items-center">
          <div className="max-w-3xl">
            <p data-reveal className="mb-5 font-mono text-sm font-semibold uppercase text-[#ff9f5f]">
              Persistent memory for coding agents
            </p>
            <h1 className="text-balance text-5xl font-semibold leading-[0.98] text-[#fff9ef] sm:text-7xl lg:text-8xl">
              {heroWords.map((word) => (
                <span className="hero-word-mask" key={word}>
                  <span data-hero-word>{word}</span>{" "}
                </span>
              ))}
            </h1>
            <p data-reveal className="mt-6 max-w-2xl text-pretty text-lg leading-8 text-[#c7d0c9] sm:text-xl">
              Orange turns completed agent sessions into reusable context: the decision, the failed attempt, the working fix, and the evidence around it.
            </p>
            <div data-reveal className="mt-8 flex flex-col gap-3 sm:flex-row">
              <a className="hero-cta-watch shimmer-button inline-flex h-12 items-center justify-center rounded-md bg-[#f26d21] px-6 text-sm font-bold text-white shadow-[0_18px_46px_rgba(242,109,33,0.28)] transition hover:scale-[1.02]" href="#story">
                See how it works
              </a>
              <a className="inline-flex h-12 items-center justify-center rounded-md border border-white/20 px-6 text-sm font-bold text-[#fff9ef] transition hover:scale-[1.02] hover:border-[#ff9f5f] hover:text-[#ffb777]" href="#graph">
                Explore the graph
              </a>
            </div>
            <div className="orange-tagline flex flex-wrap gap-x-5 gap-y-2" aria-label="Orange product properties">
              <span>Private by default</span>
              <span>Postgres + pgvector</span>
              <span>One remote MCP URL</span>
            </div>
          </div>

          <div className="relative min-h-[560px]">
            <div className="absolute inset-0 rounded-[2rem] border border-white/10 bg-[#17221c]/78 shadow-[0_34px_120px_rgba(0,0,0,0.42)] backdrop-blur-xl" />
            <div data-ping-card className="absolute inset-x-4 top-6 rounded-xl border border-white/12 bg-[#080d0a]/92 p-5 text-white shadow-2xl backdrop-blur sm:inset-x-8">
              <div className="flex items-center justify-between border-b border-white/10 pb-4">
                <div>
                  <p className="font-mono text-xs uppercase text-[#ffb36b]">recall_memory</p>
                  <p className="mt-1 text-sm text-[#d7e1d8]">relevant memory found</p>
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
                      OPTIONS returned 405 because CORS middleware was mounted after the router.
                  </p>
                </div>

                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
                  <div data-ping-line className="rounded-md border border-white/10 bg-white/[0.06] p-4">
                    <p className="font-mono text-xs text-[#ffd166]">failed path</p>
                    <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                      Expanding the origin list did not change the preflight response.
                    </p>
                  </div>
                  <div data-ping-line className="rounded-md border border-white/10 bg-white/[0.06] p-4">
                    <p className="font-mono text-xs text-[#62d49c]">worked fix</p>
                    <p className="mt-2 text-sm leading-6 text-[#d7e1d8]">
                      Mount CORSMiddleware before include_router.
                    </p>
                  </div>
                </div>
              </div>
            </div>

            <div className="absolute bottom-8 left-5 right-5 grid grid-cols-3 gap-3 sm:left-12">
              {["semantic match", "linked evidence", "agent context"].map((label, index) => (
                <div data-hero-metric className="rounded-md border border-white/12 bg-white/88 p-4 text-[#17221c] shadow-[0_18px_42px_rgba(0,0,0,0.18)] backdrop-blur" key={label}>
                  <p className="font-mono text-xs text-[#c5551c]">0{index + 1}</p>
                  <p className="mt-3 text-sm font-semibold">{label}</p>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section className="border-y border-white/10 bg-[#101713]">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 px-5 py-8 sm:px-8">
          <p className="w-fit rounded-full border border-[#ffb36b]/24 bg-[#ffb36b]/10 px-4 py-2 font-mono text-xs font-semibold text-[#ffd1a3]">
            Built as a top-5 infrastructure project at South Park Commons, Bengaluru.
          </p>
          <IntegrationStrip />
        </div>
      </section>

      <section id="story" data-scroll-story className="relative bg-[#f8f5ec] text-[#161b18]">
        <div className="mx-auto grid min-h-screen max-w-7xl gap-10 px-5 py-16 sm:px-8 lg:grid-cols-[0.82fr_1.18fr] lg:items-center lg:py-0">
          <div className="lg:sticky lg:top-28">
            <SectionEyebrow>Capture → Extract → Retrieve</SectionEyebrow>
            <RevealHeading className="mt-4 text-4xl font-semibold leading-tight sm:text-6xl">
              From a finished session to context the next agent can use.
            </RevealHeading>
            <div className="mt-8 grid gap-3">
              {["Finish a useful session", "Extract durable knowledge", "Recall it when relevant"].map((label, index) => (
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
                <h3 className="mt-4 text-3xl font-semibold">Orange receives the conversation after the work is done.</h3>
                <div className="mt-8 rounded-lg bg-[#111812] p-5 font-mono text-sm leading-7 text-[#dce8df]">
                  {["Turn 1 [user]: CORS preflight returns 405", "Turn 2 [assistant]: Reproduce OPTIONS locally", "Turn 3 [user]: Origin list change failed"].map((line) => (
                    <p className="type-line" data-story-type key={line}>{line}</p>
                  ))}
                </div>
              </article>

              <article className="story-panel">
                <p className="font-mono text-xs font-semibold uppercase text-[#c5551c]">Extract</p>
                <h3 className="mt-4 text-3xl font-semibold">Only information worth reusing becomes memory.</h3>
                <div className="mini-graph mt-8">
                  {["Insight", "User fact", "Company fact", "Steering"].map((node, index) => (
                    <span style={{ animationDelay: `${index * 180}ms` }} key={node}>{node}</span>
                  ))}
                </div>
              </article>

              <article className="story-panel">
                <p className="font-mono text-xs font-semibold uppercase text-[#c5551c]">Retrieve</p>
                <h3 className="mt-4 text-3xl font-semibold">The next agent gets the insight and the evidence around it.</h3>
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
              <SectionEyebrow tone="green">Available today</SectionEyebrow>
              <RevealHeading className="mt-4 text-4xl font-semibold leading-tight sm:text-6xl">
                One memory layer across the agents you already use.
              </RevealHeading>
            </div>
            <p data-reveal className="max-w-2xl text-lg leading-8 text-[#c7d0c9]">
              Connect through the open MCP endpoint, capture from Slack, or use the web demo. Every path writes to the same scoped Postgres graph.
            </p>
          </div>

          <div className="mt-12 grid gap-5 lg:grid-cols-[1.1fr_0.9fr] lg:items-stretch">
            <div data-bento-grid className="source-map-card relative min-h-[620px] overflow-hidden rounded-xl border border-white/10 bg-[#0A0A0F] p-4 shadow-[0_30px_90px_rgba(0,0,0,0.28)] sm:p-6">
              <div className="source-map-ambient absolute inset-0" />
              <svg className="source-map-lines absolute inset-0 h-full w-full" role="presentation" viewBox="0 0 100 100" preserveAspectRatio="none">
                {appConnections.map((app, index) => (
                  <g key={app.name} style={{ "--source-color": app.color, "--flow-delay": `${index * 520}ms` } as CSSProperties}>
                    <path className="source-flow-path" d={app.path} />
                    <path className="source-flow-path source-flow-path-soft" d={app.path} />
                    <circle className="source-flow-dot" r="0.9">
                      <animateMotion dur="3.2s" begin={`${index * 0.42}s`} repeatCount="indefinite" path={app.path} />
                    </circle>
                  </g>
                ))}
              </svg>

              <div className="orange-core-logo absolute left-1/2 top-[46%] z-10 -translate-x-1/2 -translate-y-1/2">
                <strong>ORANGE</strong>
                <small>shared memory</small>
              </div>

              {appConnections.map((app) => (
                <button
                  className={`source-node group absolute z-20 ${app.position}`}
                  key={app.name}
                  type="button"
                  style={{ "--source-color": app.color } as CSSProperties}
                  aria-label={`${app.name}: ${app.prompt}`}
                >
                  <span className="source-mark">
                    <BrandIcon icon={app.icon} />
                  </span>
                  <span className="source-tooltip" role="tooltip">
                    <span className="source-tooltip-accent" />
                    <span className="source-tooltip-header">
                      <span className="source-tooltip-icon">
                        <BrandIcon icon={app.icon} />
                      </span>
                      <span>{app.name}</span>
                      <span className="source-tooltip-time">· {app.time}</span>
                    </span>
                    <span className="source-tooltip-rule" />
                    <strong>&quot;{app.prompt}&quot;</strong>
                    <span className="source-tooltip-answer">→ {app.body}</span>
                  </span>
                </button>
              ))}
            </div>

            <div className="rounded-xl border border-white/10 bg-[#17221c] p-5 shadow-[0_30px_90px_rgba(0,0,0,0.28)]">
              <div className="mb-4 flex items-center justify-between border-b border-white/10 pb-4">
                <p className="font-mono text-xs font-semibold uppercase tracking-[0.16em] text-[#ffb36b]">MCP memory contract</p>
                <span className="rounded-full border border-white/12 bg-white/[0.06] px-2.5 py-1 font-mono text-xs text-[#d7e1d8]">live endpoint</span>
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
                Watch memory change as agents write to it.
              </RevealHeading>
              <p data-reveal className="mt-5 text-lg leading-8 text-[#536057]">
                Each node is a reusable decision, fact, failed attempt, or fix. Drag the graph to explore relationships; select a node to inspect exactly what another agent can recall.
              </p>
            </div>
            <div className="grid grid-cols-3 gap-3 text-center">
              <div className="rounded-lg bg-white p-4 shadow-sm">
                <p className="text-2xl font-semibold text-[#c5551c]">2</p>
                <p className="mt-1 text-xs font-semibold text-[#536057]">memory scopes</p>
              </div>
              <div className="rounded-lg bg-white p-4 shadow-sm">
                <p className="text-2xl font-semibold text-[#2f6f5e]">5s</p>
                <p className="mt-1 text-xs font-semibold text-[#536057]">live refresh</p>
              </div>
              <div className="rounded-lg bg-white p-4 shadow-sm">
                <p className="text-2xl font-semibold text-[#24352d]">1</p>
                <p className="mt-1 text-xs font-semibold text-[#536057]">source of truth</p>
              </div>
            </div>
          </div>
          <MemoryGraph />
        </div>
      </section>

      <section id="try" className="bg-white text-[#161b18]">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <div className="mb-10 max-w-3xl">
            <SectionEyebrow tone="green">Live product demo</SectionEyebrow>
            <RevealHeading className="mt-4 text-4xl font-semibold leading-tight sm:text-5xl">
              Create a memory, then watch it appear.
            </RevealHeading>
            <p data-reveal className="mt-5 text-lg leading-8 text-[#536057]">
              Sign in, choose a company scope, and discuss a real debugging decision. When you finish the conversation, Orange extracts the durable parts and the graph above refreshes automatically.
            </p>
          </div>
          <TestChat authenticatedEmail={auth?.email ?? null} />
        </div>
      </section>

      <section id="mcp" className="bg-[#1a221d] text-white">
        <div className="mx-auto max-w-7xl px-5 py-16 sm:px-8 lg:py-24">
          <SectionEyebrow>Three tools, one habit</SectionEyebrow>
          <RevealHeading className="mt-4 max-w-3xl text-4xl font-semibold leading-tight sm:text-5xl">
            Give every agent a reliable way to remember.
          </RevealHeading>
          <div className="mt-10 grid gap-4 md:grid-cols-3">
            {contextBlocks.map((item) => (
              <article data-reveal className="rounded-lg border border-white/10 bg-white/[0.06] p-6" key={item.title}>
                <h3 className="text-xl font-semibold">{item.title}</h3>
                <p className="mt-3 text-sm leading-6 text-[#d6e1d8]">{item.body}</p>
              </article>
            ))}
          </div>
          <a
            data-reveal
            href="/mcp"
            className="mt-8 inline-flex h-11 items-center justify-center rounded-md bg-[#f97316] px-5 text-sm font-bold text-white shadow-[0_14px_36px_rgba(249,115,22,0.24)] transition hover:scale-[1.02]"
          >
            Set up Orange MCP
          </a>
        </div>
      </section>

      <footer className="border-t border-white/10 bg-[#0a0f0c] text-[#aebbb2]">
        <div className="mx-auto flex max-w-7xl flex-col gap-4 px-5 py-8 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div>
            <p className="font-mono font-semibold text-[#fff9ef]">ORANGE</p>
            <p className="mt-1">Persistent memory for AI-assisted engineering.</p>
          </div>
          <div className="flex flex-wrap gap-5">
            <a className="transition hover:text-[#ffb36b]" href="#graph">Memory graph</a>
            <a className="transition hover:text-[#ffb36b]" href="/mcp">MCP setup</a>
            <a className="transition hover:text-[#ffb36b]" href="https://github.com/harsh-raj-singh/orange">GitHub</a>
          </div>
        </div>
      </footer>
    </main>
  );
}
