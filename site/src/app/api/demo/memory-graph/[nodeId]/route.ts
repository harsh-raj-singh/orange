import { NextResponse } from "next/server";

import { getDemoMemoryNodeDetailFromStore } from "@/lib/demo-memory-store";
import { backendJsonOrFallback, normalizeDemoGraphScope } from "@/lib/api";
import type { DemoMemoryNodeDetail } from "@/lib/demo-memory-graph";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    nodeId: string;
  }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { nodeId } = await context.params;
  const scope = normalizeDemoGraphScope(new URL(request.url).searchParams.get("scope"));

  const node = await backendJsonOrFallback({
    path: `/graph/nodes/${encodeURIComponent(nodeId)}/neighborhood?scope=${scope}`,
    warning: "orange_backend_node_failed",
    transform: (graph: BackendGraph): DemoMemoryNodeDetail | null => {
      const transformed = transformBackendGraph(graph, scope);
      const node = transformed.nodes.find((candidate) => candidate.id === nodeId);
      if (node) {
        return {
          ...node,
          detail: {
            ...(node as { detail?: Record<string, unknown> }).detail,
            title: node.label,
            body: node.summary,
            evidence: transformed.edges
              .filter((edge) => edge.source === nodeId || edge.target === nodeId)
              .map((edge) => `${edge.label}: ${edge.source} -> ${edge.target}`),
            relatedFiles: [],
            nextActions: ["Use this neighborhood as context when similar work appears."],
          },
        };
      }
      return null;
    },
    fallback: () => getDemoMemoryNodeDetailFromStore(nodeId),
  });

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
