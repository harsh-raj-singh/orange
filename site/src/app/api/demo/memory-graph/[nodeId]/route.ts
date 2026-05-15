import { NextResponse } from "next/server";

import { getDemoMemoryNodeDetailFromStore } from "@/lib/demo-memory-store";
import { orangeBackendFetch } from "@/lib/orange-backend";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    nodeId: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { nodeId } = await context.params;
  try {
    const graph = await orangeBackendFetch<BackendGraph>(
      `/graph/nodes/${encodeURIComponent(nodeId)}/neighborhood`,
    );
    if (graph) {
      const transformed = transformBackendGraph(graph);
      const node = transformed.nodes.find((candidate) => candidate.id === nodeId);
      if (node) {
        return NextResponse.json({
          ...node,
          detail: {
            title: node.label,
            body: node.summary,
            evidence: transformed.edges
              .filter((edge) => edge.source === nodeId || edge.target === nodeId)
              .map((edge) => `${edge.label}: ${edge.source} -> ${edge.target}`),
            relatedFiles: [],
            nextActions: ["Use this neighborhood as context when similar work appears."],
          },
        });
      }
    }
  } catch (error) {
    console.warn("orange_backend_node_failed", error);
  }

  const node = getDemoMemoryNodeDetailFromStore(nodeId);

  if (!node) {
    return NextResponse.json(
      {
        error: "Demo memory node not found",
      },
      { status: 404 },
    );
  }

  return NextResponse.json(node);
}
