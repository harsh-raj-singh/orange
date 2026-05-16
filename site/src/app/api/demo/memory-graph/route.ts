import { NextResponse } from "next/server";

import { getScopedDemoMemoryGraphSnapshot } from "@/lib/demo-memory-store";
import { backendJsonOrFallback, normalizeDemoGraphScope } from "@/lib/api";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";

export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const scope = normalizeDemoGraphScope(new URL(request.url).searchParams.get("scope"));

  return NextResponse.json(
    await backendJsonOrFallback<BackendGraph, ReturnType<typeof getScopedDemoMemoryGraphSnapshot>>({
      path: `/graph/full?scope=${scope}`,
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
