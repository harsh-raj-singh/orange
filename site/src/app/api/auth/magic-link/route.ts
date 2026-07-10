import { NextResponse } from "next/server";

import { createSupabaseServerClient } from "@/lib/supabase-server";

function safeNext(value: FormDataEntryValue | null) {
  const next = typeof value === "string" ? value : "/";
  return next.startsWith("/") && !next.startsWith("//") ? next : "/";
}

export async function POST(request: Request) {
  const formData = await request.formData();
  const email = String(formData.get("email") ?? "").trim().toLowerCase();
  const next = safeNext(formData.get("next"));
  const loginUrl = new URL("/login", request.url);
  loginUrl.searchParams.set("next", next);

  if (!email || !email.includes("@")) {
    loginUrl.searchParams.set("error", "Enter a valid email address.");
    return NextResponse.redirect(loginUrl, 303);
  }

  const callbackUrl = new URL("/auth/callback", request.url);
  callbackUrl.searchParams.set("next", next);
  const supabase = await createSupabaseServerClient();
  const { error } = await supabase.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: callbackUrl.toString(),
      shouldCreateUser: true,
    },
  });

  if (error) {
    loginUrl.searchParams.set("error", error.message);
  } else {
    loginUrl.searchParams.set("sent", "1");
  }
  return NextResponse.redirect(loginUrl, 303);
}
