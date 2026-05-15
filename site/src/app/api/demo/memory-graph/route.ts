import { NextResponse } from "next/server";

import { getDemoMemoryGraphSnapshot } from "@/lib/demo-memory-store";
import { orangeBackendFetch } from "@/lib/orange-backend";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";

export const dynamic = "force-dynamic";

export async function GET() {
  try {
    const graph = await orangeBackendFetch<BackendGraph>("/graph/full");
    if (graph) {
      return NextResponse.json({
        generatedAt: new Date().toISOString(),
        ...transformBackendGraph(graph),
        persisted: true,
      });
    }
  } catch (error) {
    console.warn("orange_backend_graph_failed", error);
  }

  return NextResponse.json(getDemoMemoryGraphSnapshot());
}
