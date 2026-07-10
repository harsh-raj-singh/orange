import { redirect } from "next/navigation";

import { createSupabaseServerClient } from "@/lib/supabase-server";

type ConsentPageProps = {
  searchParams: Promise<{ authorization_id?: string }>;
};

export const dynamic = "force-dynamic";

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
    <main className="min-h-screen bg-[#0d1210] px-5 py-12 text-white sm:px-8">
      <section className="mx-auto max-w-xl rounded-xl border border-white/10 bg-white/[0.04] p-6 shadow-2xl sm:p-8">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#f9a66b]">ORANGE MCP</p>
        <h1 className="mt-4 text-4xl font-semibold">Allow {details.client.name} to use Orange?</h1>
        <p className="mt-4 text-sm leading-6 text-[#b8c3ba]">
          Signed in as <span className="font-semibold text-white">{userData.user.email}</span>. Orange will use this verified identity to isolate your private memory.
        </p>

        <div className="mt-7 rounded-lg border border-white/10 bg-black/20 p-4">
          <p className="text-sm font-semibold">Requested access</p>
          <ul className="mt-3 grid gap-2 text-sm text-[#cbd8cf]">
            {scopes.map((scope) => (
              <li key={scope} className="flex items-center gap-2">
                <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-[#f97316]" />
                {scope}
              </li>
            ))}
          </ul>
        </div>

        <form action="/api/oauth/decision" method="post" className="mt-7 grid grid-cols-2 gap-3">
          <input type="hidden" name="authorization_id" value={authorizationId} />
          <button
            type="submit"
            name="decision"
            value="deny"
            className="h-11 rounded-lg border border-white/15 text-sm font-bold text-[#d4ddd7] transition hover:border-white/30"
          >
            Deny
          </button>
          <button
            type="submit"
            name="decision"
            value="approve"
            className="h-11 rounded-lg bg-[#f26d21] text-sm font-bold text-white transition hover:bg-[#ff7a2a]"
          >
            Allow access
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
