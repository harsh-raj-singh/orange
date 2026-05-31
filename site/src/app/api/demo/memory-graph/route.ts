import { NextResponse } from "next/server";

import { getDemoMemoryGraph } from "@/lib/demo-memory-graph";
import { backendJsonOrFallback, normalizeDemoGraphScope } from "@/lib/api";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";

export const revalidate = 30;

const GRAPH_CACHE_HEADERS = {
  "Cache-Control": "s-maxage=30, stale-while-revalidate=60",
};

const GRAPH_BYPASS_CACHE_HEADERS = {
  "Cache-Control": "no-store",
};

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const scope = normalizeDemoGraphScope(params.get("scope"));
  const userEmail = params.get("user_email")?.trim().toLowerCase();
  const company = params.get("company")?.trim();
  const refresh = params.has("refresh");
  const backendParams = new URLSearchParams({ scope });
  if (userEmail) {
    backendParams.set("user_email", userEmail);
    backendParams.set("user_id", userEmail);
  }
  if (company) {
    backendParams.set("company", company);
    backendParams.set("org_id", company.toLowerCase());
  }

  const data = await backendJsonOrFallback<BackendGraph, ReturnType<typeof getDemoMemoryGraph>>({
    path: `/graph/full?${backendParams.toString()}`,
    request: refresh
      ? { cache: "no-store" }
      : { next: { revalidate: 30, tags: [`memory-graph:${scope}`] } },
    warning: "orange_backend_graph_failed",
    transform: (graph) => ({
      generatedAt: new Date().toISOString(),
      ...transformBackendGraph(graph, scope),
      persisted: true,
    }),
    fallback: () => getDemoMemoryGraph(),
  });

  return NextResponse.json(data, {
    headers: refresh ? GRAPH_BYPASS_CACHE_HEADERS : GRAPH_CACHE_HEADERS,
  });
}
