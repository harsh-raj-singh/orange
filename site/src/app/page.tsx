import Image from "next/image";
import type { ReactNode } from "react";

import GrainCanvas from "@/components/grain-canvas";
import MemoryGraph from "@/components/memory-graph";
import TestChat from "@/components/test-chat";
import { getVerifiedSupabaseSession } from "@/lib/supabase-server";

const heroWords = "Your AI should remember what matters.".split(" ");

const tools = ["ChatGPT", "Claude", "Cursor", "Codex", "Slack", "Grok"];

const memories = [
  {
    eyebrow: "Decision remembered",
    title: "Use the session pooler for deployments",
    body: "The direct database connection failed on an IPv4-only host. The session pooler is the reliable path.",
    meta: "Shared with the Orange team",
    color: "orange",
  },
  {
    eyebrow: "Preference remembered",
    title: "Keep the product calm and visual",
    body: "Explain the idea with examples first. Show technical details only when someone asks for them.",
    meta: "Private to you",
    color: "violet",
  },
  {
    eyebrow: "Fix remembered",
    title: "Register middleware before routes",
    body: "That ordering fixed the preflight failure. Expanding the origin list did not.",
    meta: "Ready for the next agent",
    color: "green",
  },
];

const steps = [
  {
    number: "01",
    title: "Work naturally",
    body: "Keep using the AI tools your team already knows. Orange stays out of the way while the work happens.",
    note: "A decision is made",
  },
  {
    number: "02",
    title: "Save what matters",
    body: "At the end of a useful session, Orange keeps the decisions, fixes, preferences, and lessons worth reusing.",
    note: "The useful context is kept",
  },
  {
    number: "03",
    title: "Begin ahead",
    body: "The next person—or the next AI—starts with the right context instead of repeating old questions and mistakes.",
    note: "The next session starts smarter",
  },
];

const connectedTools = [
  { name: "Slack", role: "Team decisions", mark: "S" },
  { name: "ChatGPT", role: "Research & thinking", mark: "C" },
  { name: "Claude", role: "Deep project work", mark: "A" },
  { name: "Cursor", role: "Building & debugging", mark: "↗" },
];

function RevealHeading({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <h2 className={className}>
      <span className="line-mask">
        <span data-line-reveal>{children}</span>
      </span>
    </h2>
  );
}

function Eyebrow({ children, light = false }: { children: ReactNode; light?: boolean }) {
  return (
    <p className={`flex items-center gap-2 text-xs font-bold uppercase tracking-[0.18em] ${light ? "text-[#ffc18d]" : "text-[#b84f1b]"}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${light ? "bg-[#ff9b54]" : "bg-[#e56627]"}`} />
      {children}
    </p>
  );
}

function ArrowIcon() {
  return <span aria-hidden="true" className="text-base transition-transform group-hover:translate-x-1">→</span>;
}

export default async function Home() {
  const auth = await getVerifiedSupabaseSession();

  return (
    <main className="min-h-screen overflow-x-clip bg-[#f6f3e9] text-[#172019]">
      <header className="site-nav fixed inset-x-0 top-0 z-40">
        <nav className="mx-auto flex h-[4.5rem] max-w-[86rem] items-center justify-between px-5 sm:px-8">
          <a className="group flex items-center gap-3 text-sm font-extrabold tracking-[0.12em] text-[#fffaf0]" href="#top">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[#f2762e] text-xs text-white shadow-[0_0_24px_rgba(242,118,46,0.38)] transition-transform group-hover:rotate-6">
              O
            </span>
            ORANGE
          </a>

          <div className="hidden items-center gap-8 text-sm font-medium text-[#c8d1ca] md:flex">
            <a className="transition hover:text-white" href="#how-it-works">How it works</a>
            <a className="transition hover:text-white" href="#graph">Memory map</a>
            <a className="transition hover:text-white" href="#try">Try Orange</a>
          </div>

          {auth ? (
            <div className="flex items-center gap-3">
              <span className="hidden max-w-44 truncate text-xs text-[#b8c3ba] sm:block">{auth.email}</span>
              <form action="/api/auth/sign-out" method="post">
                <button type="submit" className="h-10 rounded-full border border-white/20 px-4 text-sm font-bold text-white transition hover:border-[#ffab70] hover:bg-white/5">
                  Sign out
                </button>
              </form>
            </div>
          ) : (
            <a className="shimmer-button inline-flex h-10 items-center justify-center rounded-full bg-[#f2762e] px-5 text-sm font-bold text-white shadow-[0_12px_32px_rgba(242,118,46,0.3)] transition hover:-translate-y-0.5" href="/login?next=%2F%23try">
              Sign in
            </a>
          )}
        </nav>
      </header>

      <section id="top" className="hero-section relative isolate min-h-[100svh] overflow-hidden bg-[#102019] pt-[4.5rem] text-white">
        <div className="absolute inset-0 -z-20">
          <Image src="/orange-hero.png" alt="" fill priority sizes="100vw" quality={85} className="object-cover object-center opacity-55 lg:object-right" />
        </div>
        <div className="absolute inset-0 -z-10 bg-[linear-gradient(90deg,#102019_0%,rgba(16,32,25,0.97)_43%,rgba(16,32,25,0.42)_76%,rgba(16,32,25,0.16)_100%)]" />
        <div className="absolute inset-0 -z-10 bg-[radial-gradient(circle_at_72%_30%,rgba(255,156,72,0.22),transparent_30%)]" />
        <div data-hero-glow className="absolute -right-36 top-16 -z-10 h-[38rem] w-[38rem] rounded-full bg-[#ff8a3d]/10 blur-[110px]" />
        <GrainCanvas />

        <div className="relative mx-auto grid min-h-[calc(100svh-4.5rem)] max-w-[86rem] items-center px-5 py-16 sm:px-8 lg:grid-cols-[1.06fr_0.94fr] lg:py-20">
          <div className="relative z-10 max-w-[49rem]">
            <div data-reveal className="mb-7 flex w-fit items-center gap-3 rounded-full border border-white/12 bg-white/[0.07] px-4 py-2 text-xs font-semibold text-[#e4ebe5] backdrop-blur">
              <span className="h-2 w-2 rounded-full bg-[#ff9953] shadow-[0_0_14px_rgba(255,153,83,0.8)]" />
              A shared memory for every AI you use
            </div>

            <h1 className="max-w-[46rem] text-balance text-[clamp(3.4rem,7vw,7.2rem)] font-semibold leading-[0.9] tracking-[-0.065em] text-[#fffaf0]">
              {heroWords.map((word) => (
                <span className="hero-word-mask" key={word}>
                  <span data-hero-word>{word}</span>{" "}
                </span>
              ))}
            </h1>

            <p data-reveal className="mt-7 max-w-[39rem] text-pretty text-lg leading-8 text-[#c9d3cc] sm:text-xl">
              Orange remembers the decisions, fixes, and context your team would otherwise lose—so every new AI conversation can start where the last one ended.
            </p>

            <div data-reveal className="mt-9 flex flex-col gap-3 sm:flex-row">
              <a className="hero-cta-watch shimmer-button group inline-flex h-13 items-center justify-center gap-3 rounded-full bg-[#f2762e] px-7 text-sm font-bold text-white shadow-[0_18px_46px_rgba(242,118,46,0.3)] transition hover:-translate-y-1" href="#try">
                Try it with your memory <ArrowIcon />
              </a>
              <a className="group inline-flex h-13 items-center justify-center gap-3 rounded-full border border-white/18 bg-white/[0.05] px-7 text-sm font-bold text-white backdrop-blur transition hover:-translate-y-1 hover:border-white/35 hover:bg-white/10" href="#how-it-works">
                See how it feels <ArrowIcon />
              </a>
            </div>

            <div className="orange-tagline flex flex-wrap gap-x-6 gap-y-2" aria-label="Orange product promises">
              <span>Useful, not noisy</span>
              <span>Private by default</span>
              <span>Shared when you choose</span>
            </div>
          </div>

          <div className="relative hidden min-h-[620px] lg:block" aria-label="Examples of memories Orange keeps">
            <div className="absolute inset-10 rounded-[2.25rem] border border-white/12 bg-[#0d1712]/54 shadow-[0_40px_140px_rgba(0,0,0,0.35)] backdrop-blur-md" />
            <p className="absolute left-16 top-16 z-10 text-xs font-bold uppercase tracking-[0.18em] text-[#f3c39f]">What Orange remembers</p>
            {memories.map((memory, index) => (
              <article
                data-ping-card
                key={memory.title}
                className={`memory-note memory-note-${memory.color} absolute z-10 w-[min(26rem,78%)] rounded-2xl border bg-[#fffdf7] p-5 text-[#172019] shadow-[0_24px_70px_rgba(0,0,0,0.28)] ${
                  index === 0 ? "left-3 top-28 -rotate-2" : index === 1 ? "right-0 top-[16.5rem] rotate-2" : "bottom-12 left-10 -rotate-1"
                }`}
              >
                <div className="flex items-center justify-between gap-4">
                  <p className="text-[0.68rem] font-extrabold uppercase tracking-[0.14em]">{memory.eyebrow}</p>
                  <span className="h-2.5 w-2.5 rounded-full bg-current opacity-65" />
                </div>
                <h2 className="mt-3 text-xl font-bold leading-6">{memory.title}</h2>
                <p className="mt-3 text-sm leading-6 text-[#5b675f]">{memory.body}</p>
                <p className="mt-5 border-t border-[#24352d]/10 pt-3 text-xs font-semibold text-[#748078]">{memory.meta}</p>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="border-y border-[#24352d]/10 bg-[#fffdf6]">
        <div className="mx-auto grid max-w-[86rem] gap-6 px-5 py-8 sm:px-8 lg:grid-cols-[auto_1fr] lg:items-center">
          <p className="text-sm font-bold text-[#49554e]">One memory, wherever work happens</p>
          <div className="flex flex-wrap gap-2 lg:justify-end">
            {tools.map((tool) => (
              <span key={tool} className="rounded-full border border-[#24352d]/10 bg-[#f4f1e8] px-4 py-2 text-xs font-bold text-[#5a665f]">{tool}</span>
            ))}
          </div>
        </div>
      </section>

      <section id="how-it-works" className="relative overflow-hidden bg-[#f6f3e9] py-24 sm:py-32">
        <div className="pointer-events-none absolute -right-40 top-24 h-96 w-96 rounded-full bg-[#f4b26f]/20 blur-3xl" />
        <div className="mx-auto max-w-[86rem] px-5 sm:px-8">
          <div className="grid gap-10 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
            <div>
              <Eyebrow>How Orange works</Eyebrow>
              <RevealHeading className="mt-5 max-w-xl text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.045em] text-[#18221c] sm:text-6xl">
                Memory that feels effortless.
              </RevealHeading>
            </div>
            <p data-reveal className="max-w-2xl text-lg leading-8 text-[#5f6b64] lg:justify-self-end">
              You do not need to organize a knowledge base or teach every tool your history. Orange quietly turns useful moments into context that can be found again.
            </p>
          </div>

          <div className="mt-16 grid gap-5 lg:grid-cols-3">
            {steps.map((step) => (
              <article data-reveal key={step.number} className="group relative overflow-hidden rounded-[1.75rem] border border-[#24352d]/10 bg-[#fffdf7] p-7 shadow-[0_24px_70px_rgba(36,53,45,0.08)] transition duration-300 hover:-translate-y-2 hover:shadow-[0_34px_90px_rgba(36,53,45,0.14)] sm:p-8">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-extrabold tracking-[0.18em] text-[#c05a25]">{step.number}</span>
                  <span className="h-10 w-10 rounded-full border border-[#24352d]/10 bg-[#f6f3e9] transition group-hover:scale-110 group-hover:bg-[#ffead8]" />
                </div>
                <h3 className="mt-14 text-3xl font-semibold tracking-[-0.035em] text-[#18221c]">{step.title}</h3>
                <p className="mt-4 text-[0.98rem] leading-7 text-[#667169]">{step.body}</p>
                <div className="mt-10 flex items-center gap-3 border-t border-[#24352d]/10 pt-5 text-xs font-bold text-[#526057]">
                  <span className="grid h-7 w-7 place-items-center rounded-full bg-[#e9f3eb] text-[#2f6f5e]">✓</span>
                  {step.note}
                </div>
              </article>
            ))}
          </div>
        </div>
      </section>

      <section className="bg-[#17271f] py-24 text-white sm:py-32">
        <div className="mx-auto max-w-[86rem] px-5 sm:px-8">
          <div className="mx-auto max-w-4xl text-center">
            <Eyebrow light>The difference</Eyebrow>
            <RevealHeading className="mt-5 text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.045em] sm:text-6xl">
              Stop paying the context tax.
            </RevealHeading>
            <p data-reveal className="mx-auto mt-6 max-w-2xl text-lg leading-8 text-[#b9c7be]">
              Your team already solved it, chose it, or learned it. Orange makes sure that work is not lost between conversations.
            </p>
          </div>

          <div className="mx-auto mt-14 grid max-w-5xl gap-5 lg:grid-cols-2">
            <article data-reveal className="rounded-[1.75rem] border border-white/10 bg-black/15 p-7 sm:p-9">
              <p className="text-xs font-extrabold uppercase tracking-[0.16em] text-[#e8a27c]">Without Orange</p>
              <p className="mt-7 text-3xl font-semibold leading-tight text-[#eef2ee]">“Can you explain the project again?”</p>
              <ul className="mt-8 grid gap-4 text-sm leading-6 text-[#9faea5]">
                <li className="flex gap-3"><span className="text-[#e8895c]">×</span> Decisions disappear into old chats</li>
                <li className="flex gap-3"><span className="text-[#e8895c]">×</span> Failed approaches get repeated</li>
                <li className="flex gap-3"><span className="text-[#e8895c]">×</span> Every session begins with a briefing</li>
              </ul>
            </article>
            <article data-reveal className="relative overflow-hidden rounded-[1.75rem] border border-[#ff9f5f]/30 bg-[linear-gradient(145deg,rgba(242,118,46,0.2),rgba(255,255,255,0.07))] p-7 shadow-[0_24px_80px_rgba(242,118,46,0.12)] sm:p-9">
              <div className="absolute -right-12 -top-12 h-40 w-40 rounded-full bg-[#ff9853]/20 blur-3xl" />
              <p className="text-xs font-extrabold uppercase tracking-[0.16em] text-[#ffc69f]">With Orange</p>
              <p className="mt-7 text-3xl font-semibold leading-tight text-white">“I found the last decision. Here is where we left off.”</p>
              <ul className="mt-8 grid gap-4 text-sm leading-6 text-[#d9e2dc]">
                <li className="flex gap-3"><span className="text-[#76dca9]">✓</span> The useful decision is ready</li>
                <li className="flex gap-3"><span className="text-[#76dca9]">✓</span> Evidence and context stay connected</li>
                <li className="flex gap-3"><span className="text-[#76dca9]">✓</span> New work starts with momentum</li>
              </ul>
            </article>
          </div>
        </div>
      </section>

      <section id="connected" className="bg-[#fffdf7] py-24 sm:py-32">
        <div className="mx-auto grid max-w-[86rem] gap-14 px-5 sm:px-8 lg:grid-cols-[0.8fr_1.2fr] lg:items-center">
          <div>
            <Eyebrow>One shared memory</Eyebrow>
            <RevealHeading className="mt-5 text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.045em] sm:text-6xl">
              Your tools finally know what the others learned.
            </RevealHeading>
            <p data-reveal className="mt-6 max-w-xl text-lg leading-8 text-[#657069]">
              A decision from Slack can guide tomorrow&apos;s build. A fix discovered in Cursor can help a teammate in ChatGPT. Orange keeps the memory in one place.
            </p>
            <a data-reveal href="/mcp" className="group mt-8 inline-flex items-center gap-3 text-sm font-extrabold text-[#a84718]">
              Connect the tools you use <ArrowIcon />
            </a>
          </div>

          <div className="relative min-h-[34rem] rounded-[2rem] border border-[#24352d]/10 bg-[#f2f0e6] p-5 shadow-[0_30px_90px_rgba(36,53,45,0.1)] sm:p-8">
            <div className="absolute left-1/2 top-1/2 z-10 grid h-32 w-32 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border-[10px] border-[#fffdf7] bg-[#f2762e] text-center shadow-[0_20px_60px_rgba(242,118,46,0.28)]">
              <div>
                <strong className="block text-sm tracking-[0.12em] text-white">ORANGE</strong>
                <span className="mt-1 block text-[0.62rem] font-semibold text-[#ffe3d1]">shared memory</span>
              </div>
            </div>
            <div className="grid h-full min-h-[30rem] grid-cols-2 gap-4">
              {connectedTools.map((tool, index) => (
                <article key={tool.name} className={`relative flex min-h-52 flex-col justify-between rounded-2xl border border-[#24352d]/10 bg-[#fffdf7] p-5 shadow-[0_16px_40px_rgba(36,53,45,0.08)] ${index % 2 ? "items-end text-right" : ""}`}>
                  <span className="grid h-11 w-11 place-items-center rounded-xl bg-[#17271f] text-sm font-black text-white">{tool.mark}</span>
                  <div>
                    <h3 className="text-xl font-bold text-[#1d2821]">{tool.name}</h3>
                    <p className="mt-1 text-sm text-[#748078]">{tool.role}</p>
                  </div>
                </article>
              ))}
            </div>
          </div>
        </div>
      </section>

      <section id="graph" className="border-y border-[#24352d]/10 bg-[#edf2eb] py-24 sm:py-32">
        <div className="mx-auto max-w-[86rem] px-5 sm:px-8">
          <div className="mb-12 grid gap-8 lg:grid-cols-[1fr_auto] lg:items-end">
            <div className="max-w-3xl">
              <div className="flex items-center gap-3">
                <Eyebrow>Your living memory map</Eyebrow>
                <span className="live-badge"><span /> Live</span>
              </div>
              <RevealHeading className="mt-5 text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.045em] sm:text-6xl">
                See what your team knows.
              </RevealHeading>
              <p data-reveal className="mt-6 max-w-2xl text-lg leading-8 text-[#5f6c64]">
                Every card is a useful memory. Follow the connections, open any note, and switch between your private context and the knowledge shared with your workspace.
              </p>
            </div>
            <div className="flex gap-3">
              <div className="rounded-2xl border border-[#24352d]/10 bg-white px-5 py-4 shadow-sm">
                <p className="text-2xl font-semibold text-[#b84f1b]">2</p>
                <p className="mt-1 text-xs font-bold text-[#6a766f]">ways to remember</p>
              </div>
              <div className="rounded-2xl border border-[#24352d]/10 bg-white px-5 py-4 shadow-sm">
                <p className="text-2xl font-semibold text-[#2f6f5e]">Live</p>
                <p className="mt-1 text-xs font-bold text-[#6a766f]">always in sync</p>
              </div>
            </div>
          </div>
          <MemoryGraph />
        </div>
      </section>

      <section id="try" className="relative overflow-hidden bg-[#fffdf7] py-24 sm:py-32">
        <div className="absolute -left-44 top-24 h-96 w-96 rounded-full bg-[#ffbc7a]/18 blur-3xl" />
        <div className="relative mx-auto max-w-[86rem] px-5 sm:px-8">
          <div className="mb-12 grid gap-8 lg:grid-cols-[0.8fr_1.2fr] lg:items-end">
            <div>
              <Eyebrow>Try Orange</Eyebrow>
              <RevealHeading className="mt-5 text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.045em] sm:text-6xl">
                Give it something worth remembering.
              </RevealHeading>
            </div>
            <p data-reveal className="max-w-2xl text-lg leading-8 text-[#647068] lg:justify-self-end">
              Talk through a real decision, lesson, or fix. When you finish, Orange turns the useful parts into memory and adds them to the map above.
            </p>
          </div>
          <TestChat authenticatedEmail={auth?.email ?? null} />
        </div>
      </section>

      <section className="relative overflow-hidden bg-[#102019] py-24 text-white sm:py-32">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_78%_50%,rgba(242,118,46,0.24),transparent_30%)]" />
        <div className="relative mx-auto flex max-w-[86rem] flex-col gap-10 px-5 sm:px-8 lg:flex-row lg:items-end lg:justify-between">
          <div className="max-w-4xl">
            <Eyebrow light>Ready when you are</Eyebrow>
            <RevealHeading className="mt-5 text-balance text-5xl font-semibold leading-[0.98] tracking-[-0.05em] sm:text-7xl">
              Let the next conversation begin ahead.
            </RevealHeading>
          </div>
          <a href="/mcp" className="shimmer-button group inline-flex h-14 shrink-0 items-center justify-center gap-3 rounded-full bg-[#f2762e] px-7 text-sm font-bold text-white shadow-[0_18px_46px_rgba(242,118,46,0.3)] transition hover:-translate-y-1">
            Connect Orange <ArrowIcon />
          </a>
        </div>
      </section>

      <footer className="border-t border-white/10 bg-[#0b1510] text-[#9daba1]">
        <div className="mx-auto flex max-w-[86rem] flex-col gap-6 px-5 py-9 text-sm sm:flex-row sm:items-center sm:justify-between sm:px-8">
          <div className="flex items-center gap-3">
            <span className="grid h-8 w-8 place-items-center rounded-full bg-[#f2762e] text-xs font-black text-white">O</span>
            <div>
              <p className="font-extrabold tracking-[0.12em] text-white">ORANGE</p>
              <p className="mt-0.5 text-xs">Memory for every AI you use.</p>
            </div>
          </div>
          <div className="flex flex-wrap gap-6">
            <a className="transition hover:text-white" href="#how-it-works">How it works</a>
            <a className="transition hover:text-white" href="#graph">Memory map</a>
            <a className="transition hover:text-white" href="/mcp">Connect</a>
            <a className="transition hover:text-white" href="https://github.com/harsh-raj-singh/orange">GitHub</a>
          </div>
        </div>
      </footer>
    </main>
  );
}
