import Link from "next/link";

type LoginPageProps = {
  searchParams: Promise<{
    next?: string;
    sent?: string;
    error?: string;
  }>;
};

function safeNext(value: string | undefined) {
  return value?.startsWith("/") && !value.startsWith("//") ? value : "/";
}

export default async function LoginPage({ searchParams }: LoginPageProps) {
  const params = await searchParams;
  const next = safeNext(params.next);

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#0a0f0c] px-5 py-7 text-white sm:px-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_18%_28%,rgba(249,115,22,0.2),transparent_30%),radial-gradient(circle_at_84%_70%,rgba(98,212,156,0.08),transparent_28%)]" />
      <div className="relative mx-auto max-w-6xl">
        <Link href="/" className="flex w-fit items-center gap-2 font-mono text-sm font-semibold tracking-[0.08em]">
          <span className="h-2.5 w-2.5 rounded-full bg-[#f97316] shadow-[0_0_20px_rgba(249,115,22,0.7)]" />
          ORANGE
        </Link>

        <div className="grid min-h-[calc(100vh-5rem)] gap-12 py-12 lg:grid-cols-[1fr_0.82fr] lg:items-center">
          <section className="max-w-2xl">
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#f9a66b]">Your Orange account</p>
            <h1 className="mt-5 text-balance text-5xl font-semibold leading-[1.04] sm:text-6xl">See what your agents remember.</h1>
            <p className="mt-6 max-w-xl text-lg leading-8 text-[#b8c3ba]">
              Sign in to view your private graph, test memory capture, and authorize MCP clients. The same account scopes your memory everywhere.
            </p>
            <div className="mt-8 grid gap-3 text-sm text-[#dbe7df] sm:grid-cols-3 lg:max-w-xl">
              {["Private graph", "Browser-based MCP login", "No passwords stored by Orange"].map((item) => (
                <div key={item} className="rounded-xl border border-white/10 bg-white/[0.04] p-4">{item}</div>
              ))}
            </div>
          </section>

          <section className="rounded-2xl border border-white/10 bg-[#111713]/90 p-6 shadow-[0_30px_100px_rgba(0,0,0,0.38)] backdrop-blur sm:p-8">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#f9a66b]">
            Sign in with a magic link
          </p>
          <h2 className="mt-4 text-3xl font-semibold">Continue to Orange</h2>
          <p className="mt-3 text-sm leading-6 text-[#aebbb2]">
            Enter your email and open the secure link we send. No password is required.
          </p>

          {params.sent === "1" ? (
            <p className="mt-6 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-100">
              Link sent. Open the email on this device to finish signing in.
            </p>
          ) : null}
          {params.error ? (
            <p className="mt-6 rounded-lg border border-red-400/20 bg-red-400/10 px-4 py-3 text-sm text-red-100">
              {params.error}
            </p>
          ) : null}

          <form action="/api/auth/magic-link" method="post" className="mt-7 grid gap-4">
            <input type="hidden" name="next" value={next} />
            <label className="grid gap-2 text-sm font-medium" htmlFor="email">
              Work email
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                placeholder="you@company.com"
                className="h-12 rounded-lg border border-white/15 bg-black/20 px-4 text-white outline-none transition placeholder:text-[#708078] focus:border-[#f97316]"
              />
            </label>
            <button
              type="submit"
              className="h-12 rounded-lg bg-[#f26d21] px-5 text-sm font-bold text-white transition hover:bg-[#ff7a2a]"
            >
              Send magic link
            </button>
          </form>
          <p className="mt-5 text-xs leading-5 text-[#78867d]">Orange uses Supabase Auth to verify your identity. Your email is never used as an unverified memory key.</p>
          </section>
        </div>
      </div>
    </main>
  );
}
