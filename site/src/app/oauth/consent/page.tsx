import { redirect } from "next/navigation";

import { createSupabaseServerClient } from "@/lib/supabase-server";

type ConsentPageProps = {
  searchParams: Promise<{ authorization_id?: string }>;
};

export const dynamic = "force-dynamic";

const scopeLabels: Record<string, string> = {
  openid: "Verify your Orange account",
  email: "Use your verified email to isolate private memory",
  profile: "Read basic account details",
  offline_access: "Stay connected when the client refreshes its session",
};

export default async function ConsentPage({ searchParams }: ConsentPageProps) {
  const { authorization_id: authorizationId } = await searchParams;
  if (!authorizationId) {
    return <ConsentError message="Missing authorization request." />;
  }

  const supabase = await createSupabaseServerClient();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) {
    redirect(`/login?next=${encodeURIComponent(`/oauth/consent?authorization_id=${authorizationId}`)}`);
  }

  const { data: details, error } = await supabase.auth.oauth.getAuthorizationDetails(authorizationId);
  if (error || !details) {
    return <ConsentError message={error?.message ?? "This authorization request is no longer valid."} />;
  }
  if (!("authorization_id" in details)) {
    redirect(details.redirect_url);
  }

  const scopes = details.scope.split(" ").filter(Boolean);

  return (
    <main className="relative flex min-h-screen items-center overflow-hidden bg-[#0a0f0c] px-5 py-12 text-white sm:px-8">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(249,115,22,0.18),transparent_34%)]" />
      <section className="relative mx-auto w-full max-w-xl rounded-2xl border border-white/10 bg-[#111713]/95 p-6 shadow-[0_30px_100px_rgba(0,0,0,0.42)] sm:p-8">
        <div className="flex items-center gap-2 font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#f9a66b]">
          <span className="h-2 w-2 rounded-full bg-[#f97316]" /> Orange MCP connection
        </div>
        <h1 className="mt-5 text-balance text-4xl font-semibold">Connect {details.client.name} to your memory?</h1>
        <p className="mt-4 text-sm leading-6 text-[#b8c3ba]">
          You are signed in as <span className="font-semibold text-white">{userData.user.email}</span>. If you continue, this client can use Orange&apos;s memory tools on your behalf.
        </p>

        <div className="mt-7 rounded-xl border border-white/10 bg-black/20 p-4">
          <p className="text-sm font-semibold">This connection can</p>
          <ul className="mt-3 grid gap-2 text-sm text-[#cbd8cf]">
            {scopes.map((scope) => (
              <li key={scope} className="flex items-center gap-2">
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#f97316]" />
                {scopeLabels[scope] ?? scope}
              </li>
            ))}
          </ul>
        </div>

        <p className="mt-4 text-xs leading-5 text-[#849188]">Orange never gives the client your password. You can remove the MCP connection from the client at any time.</p>

        <form action="/api/oauth/decision" method="post" className="mt-7 grid grid-cols-2 gap-3">
          <input type="hidden" name="authorization_id" value={authorizationId} />
          <button
            type="submit"
            name="decision"
            value="deny"
            className="h-11 rounded-lg border border-white/15 text-sm font-bold text-[#d4ddd7] transition hover:border-white/30"
          >
            Cancel
          </button>
          <button
            type="submit"
            name="decision"
            value="approve"
            className="h-11 rounded-lg bg-[#f26d21] text-sm font-bold text-white transition hover:bg-[#ff7a2a]"
          >
            Connect client
          </button>
        </form>
      </section>
    </main>
  );
}

function ConsentError({ message }: { message: string }) {
  return (
    <main className="flex min-h-screen items-center justify-center bg-[#0d1210] px-5 text-white">
      <div className="max-w-lg rounded-xl border border-red-400/20 bg-red-400/10 p-6">
        <h1 className="text-2xl font-semibold">Authorization failed</h1>
        <p className="mt-3 text-sm leading-6 text-red-100">{message}</p>
      </div>
    </main>
  );
}
