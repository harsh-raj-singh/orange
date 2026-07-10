import { NextResponse } from "next/server";

import { getDemoMemoryGraph } from "@/lib/demo-memory-graph";
import { backendJsonOrFallback, normalizeDemoGraphScope } from "@/lib/api";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";
import { getVerifiedSupabaseSession } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

const GRAPH_NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
  "CDN-Cache-Control": "no-store",
  "Vercel-CDN-Cache-Control": "no-store",
};

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const scope = normalizeDemoGraphScope(params.get("scope"));
  const company = params.get("company")?.trim();
  const auth = await getVerifiedSupabaseSession();

  if (!auth) {
    return NextResponse.json(
      {
        ...getDemoMemoryGraph(),
        persisted: false,
        source: "fallback",
      },
      { headers: GRAPH_NO_STORE_HEADERS },
    );
  }

  const backendParams = new URLSearchParams({ scope });
  backendParams.set("user_email", auth.email);
  backendParams.set("user_id", auth.userId);
  if (company) {
    backendParams.set("company", company);
    backendParams.set("org_id", company.toLowerCase());
  }

  const data = await backendJsonOrFallback<BackendGraph, ReturnType<typeof getDemoMemoryGraph>>({
    path: `/graph/full?${backendParams.toString()}`,
    request: {
      cache: "no-store",
      headers: { Authorization: `Bearer ${auth.accessToken}` },
    },
    warning: "orange_backend_graph_failed",
    transform: (graph) => ({
      generatedAt: new Date().toISOString(),
      ...transformBackendGraph(graph, scope),
      persisted: true,
    }),
    fallback: () => getDemoMemoryGraph(),
  });

  return NextResponse.json(data, {
    headers: GRAPH_NO_STORE_HEADERS,
  });
}
