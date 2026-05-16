import { NextResponse } from "next/server";

import { getScopedDemoMemoryGraphSnapshot } from "@/lib/demo-memory-store";
import { backendJsonOrFallback, normalizeDemoGraphScope } from "@/lib/api";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const scope = normalizeDemoGraphScope(params.get("scope"));
  const userEmail = params.get("user_email")?.trim().toLowerCase();
  const backendParams = new URLSearchParams({ scope });
  if (userEmail) {
    backendParams.set("user_email", userEmail);
    backendParams.set("user_id", userEmail);
  }

  return NextResponse.json(
    await backendJsonOrFallback<BackendGraph, ReturnType<typeof getScopedDemoMemoryGraphSnapshot>>({
      path: `/graph/full?${backendParams.toString()}`,
      warning: "orange_backend_graph_failed",
      transform: (graph) => ({
        generatedAt: new Date().toISOString(),
        ...transformBackendGraph(graph, scope),
        persisted: true,
      }),
      fallback: () => getScopedDemoMemoryGraphSnapshot(scope),
    }),
  );
}
