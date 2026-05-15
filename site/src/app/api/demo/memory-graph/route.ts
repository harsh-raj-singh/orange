import { NextResponse } from "next/server";

import { getScopedDemoMemoryGraphSnapshot } from "@/lib/demo-memory-store";
import { orangeBackendFetch } from "@/lib/orange-backend";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";

export const dynamic = "force-dynamic";

function normalizeScope(value: string | null) {
  return value === "user" || value === "global" || value === "both" ? value : "both";
}

export async function GET(request: Request) {
  const scope = normalizeScope(new URL(request.url).searchParams.get("scope"));

  try {
    const graph = await orangeBackendFetch<BackendGraph>(`/graph/full?scope=${scope}`);
    if (graph) {
      return NextResponse.json({
        generatedAt: new Date().toISOString(),
        ...transformBackendGraph(graph, scope),
        persisted: true,
      });
    }
  } catch (error) {
    console.warn("orange_backend_graph_failed", error);
  }

  return NextResponse.json(getScopedDemoMemoryGraphSnapshot(scope));
}
