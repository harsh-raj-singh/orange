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
    <main className="min-h-screen bg-[#0d1210] px-5 py-10 text-white sm:px-8">
      <div className="mx-auto max-w-lg">
        <Link href="/" className="font-mono text-sm font-semibold">
          ORANGE
        </Link>

        <section className="mt-16 rounded-xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl sm:p-8">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#f9a66b]">
            Secure sign in
          </p>
          <h1 className="mt-4 text-4xl font-semibold">Connect your agent to your memory.</h1>
          <p className="mt-4 text-sm leading-6 text-[#b8c3ba]">
            Enter your email. Supabase sends a secure magic link; Orange never asks you to copy an API key or MCP token.
          </p>

          {params.sent === "1" ? (
            <p className="mt-6 rounded-lg border border-emerald-400/20 bg-emerald-400/10 px-4 py-3 text-sm text-emerald-100">
              Check your inbox and open the Orange sign-in link in this browser.
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
              Email
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
              Email me a secure link
            </button>
          </form>
        </section>
      </div>
    </main>
  );
}
