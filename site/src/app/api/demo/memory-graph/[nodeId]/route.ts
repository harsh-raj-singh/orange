import { NextResponse } from "next/server";

import { getDemoMemoryNodeDetail } from "@/lib/demo-memory-graph";
import { backendJsonOrFallback, normalizeDemoGraphScope } from "@/lib/api";
import type { DemoMemoryNodeDetail } from "@/lib/demo-memory-graph";
import { transformBackendGraph, type BackendGraph } from "@/lib/orange-graph-transform";
import { getVerifiedSupabaseSession } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

const GRAPH_NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
  "CDN-Cache-Control": "no-store",
  "Vercel-CDN-Cache-Control": "no-store",
};

type RouteContext = {
  params: Promise<{
    nodeId: string;
  }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { nodeId } = await context.params;
  const params = new URL(request.url).searchParams;
  const scope = normalizeDemoGraphScope(params.get("scope"));
  const company = params.get("company")?.trim();
  const auth = await getVerifiedSupabaseSession();

  if (!auth) {
    const previewNode = getDemoMemoryNodeDetail(nodeId);
    return previewNode
      ? NextResponse.json(previewNode, { headers: GRAPH_NO_STORE_HEADERS })
      : NextResponse.json({ error: "Preview memory node not found" }, { status: 404 });
  }

  const backendParams = new URLSearchParams({
    scope,
    user_email: auth.email,
    user_id: auth.userId,
    ...(company ? { company } : {}),
    ...(company ? { org_id: company.toLowerCase() } : {}),
  });

  const node = await backendJsonOrFallback({
    path: `/graph/nodes/${encodeURIComponent(nodeId)}/neighborhood?${backendParams.toString()}`,
    request: {
      cache: "no-store",
      headers: { Authorization: `Bearer ${auth.accessToken}` },
    },
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
    fallback: () => getDemoMemoryNodeDetail(nodeId),
  });

  if (!node) {
    return NextResponse.json(
      {
        error: "Demo memory node not found",
      },
      { status: 404 },
    );
  }

  return NextResponse.json(node, {
    headers: GRAPH_NO_STORE_HEADERS,
  });
}
