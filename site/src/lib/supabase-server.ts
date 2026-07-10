import { createServerClient } from "@supabase/ssr";
import { cookies } from "next/headers";

function requiredEnvironment(name: "NEXT_PUBLIC_SUPABASE_URL" | "NEXT_PUBLIC_SUPABASE_ANON_KEY") {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for Orange authentication.`);
  }
  return value;
}

export async function createSupabaseServerClient() {
  const cookieStore = await cookies();

  return createServerClient(
    requiredEnvironment("NEXT_PUBLIC_SUPABASE_URL"),
    requiredEnvironment("NEXT_PUBLIC_SUPABASE_ANON_KEY"),
    {
      cookies: {
        getAll: () => cookieStore.getAll(),
        setAll: (cookiesToSet) => {
          try {
            cookiesToSet.forEach(({ name, value, options }) => {
              cookieStore.set(name, value, options);
            });
          } catch {
            // Server Components can read cookies but cannot write them. Route
            // handlers using this helper perform the actual refresh writes.
          }
        },
      },
    },
  );
}

export type VerifiedSupabaseSession = {
  accessToken: string;
  email: string;
  userId: string;
};

export async function getVerifiedSupabaseSession(): Promise<VerifiedSupabaseSession | null> {
  try {
    const supabase = await createSupabaseServerClient();
    const {
      data: { session },
      error: sessionError,
    } = await supabase.auth.getSession();

    if (sessionError || !session?.access_token) {
      return null;
    }

    const { data: claimsData, error: claimsError } = await supabase.auth.getClaims(
      session.access_token,
    );
    const subject = claimsData?.claims.sub;
    const email = claimsData?.claims.email;

    if (
      claimsError ||
      typeof subject !== "string" ||
      !subject ||
      typeof email !== "string" ||
      !email.includes("@")
    ) {
      return null;
    }

    return {
      accessToken: session.access_token,
      email: email.trim().toLowerCase(),
      userId: subject,
    };
  } catch {
    return null;
  }
}
