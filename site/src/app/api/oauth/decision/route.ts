import { NextResponse } from "next/server";

import { createSupabaseServerClient } from "@/lib/supabase-server";

export async function POST(request: Request) {
  const formData = await request.formData();
  const authorizationId = String(formData.get("authorization_id") ?? "").trim();
  const decision = formData.get("decision");
  if (!authorizationId || (decision !== "approve" && decision !== "deny")) {
    return NextResponse.json({ error: "Invalid authorization decision." }, { status: 400 });
  }

  const supabase = await createSupabaseServerClient();
  const { data: userData } = await supabase.auth.getUser();
  if (!userData.user) {
    const next = `/oauth/consent?authorization_id=${encodeURIComponent(authorizationId)}`;
    return NextResponse.redirect(new URL(`/login?next=${encodeURIComponent(next)}`, request.url), 303);
  }

  const result = decision === "approve"
    ? await supabase.auth.oauth.approveAuthorization(authorizationId)
    : await supabase.auth.oauth.denyAuthorization(authorizationId);

  if (result.error || !result.data) {
    return NextResponse.json(
      { error: result.error?.message ?? "Authorization could not be completed." },
      { status: 400 },
    );
  }
  return NextResponse.redirect(result.data.redirect_url, 303);
}
