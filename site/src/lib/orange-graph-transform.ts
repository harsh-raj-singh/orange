import type { DemoMemoryEdge, DemoMemoryNode, DemoMemoryNodeType } from "@/lib/demo-memory-graph";

type BackendNode = {
  id?: string;
  label?: string;
  properties?: Record<string, unknown>;
};

type BackendEdge = {
  source?: string;
  target?: string;
  type?: string;
  properties?: Record<string, unknown>;
};

export type BackendGraph = {
  nodes?: BackendNode[];
  edges?: BackendEdge[];
};

type MemoryScope = "user" | "global" | "both";

function asString(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function statusFor(label?: string): DemoMemoryNode["metadata"]["status"] {
  if (label === "Solution") {
    return "resolved";
  }
  if (label === "Problem") {
    return "open";
  }
  return "active";
}

function nodeTypeFor(label?: string): DemoMemoryNodeType {
  if (
    label === "Problem" ||
    label === "Solution" ||
    label === "Attempt" ||
    label === "Artifact" ||
    label === "Concept" ||
    label === "Session"
  ) {
    return label;
  }
  return "Concept";
}

function scopeFor(properties: Record<string, unknown>, fallback: MemoryScope) {
  const rawScope =
    asString(properties.scope) ??
    asString(properties.visibility) ??
    asString(properties.memory_scope);

  if (rawScope === "global" || rawScope === "shared") {
    return "global";
  }

  if (rawScope === "user" || rawScope === "private") {
    return "user";
  }

  return fallback === "global" ? "global" : "user";
}

export function transformBackendGraph(graph: BackendGraph, requestedScope: MemoryScope = "both") {
  const nodes = (graph.nodes ?? [])
    .map((node): DemoMemoryNode | null => {
      const id = asString(node.id);
      if (!id) {
        return null;
      }
      const properties = node.properties ?? {};
      const nodeType = nodeTypeFor(asString(node.label));
      const scope = scopeFor(properties, requestedScope);
      const label =
        asString(properties.canonical_label) ??
        asString(properties.title) ??
        asString(properties.locator) ??
        id;
      const summary =
        asString(properties.description) ??
        asString(properties.in_depth_summary) ??
        asString(properties.summary) ??
        asString(properties.context_brief) ??
        "Stored Orange memory.";

      return {
        id,
        label,
        type: nodeType,
        summary,
        score: asNumber(properties.score) ?? 0.9,
        metadata: {
          owner: asString(properties.user_id) ?? asString(properties.org_id),
          repo: asString(properties.source) ?? "orange-backend",
          createdAt:
            asString(properties.created_at) ??
            asString(properties.ingested_at) ??
            new Date().toISOString(),
          status: statusFor(nodeType),
          scope,
        } as DemoMemoryNode["metadata"] & { scope: Exclude<MemoryScope, "both"> },
      } satisfies DemoMemoryNode;
    })
    .filter((node): node is DemoMemoryNode => Boolean(node))
    .filter((node) => {
      if (requestedScope === "both") {
        return true;
      }

      return (node.metadata as DemoMemoryNode["metadata"] & { scope?: MemoryScope }).scope === requestedScope;
    });
  const visibleNodeIds = new Set(nodes.map((node) => node.id));

  const edges: DemoMemoryEdge[] = (graph.edges ?? [])
    .map((edge, index) => {
      const source = asString(edge.source);
      const target = asString(edge.target);
      if (!source || !target) {
        return null;
      }

      return {
        id: `${source}-${edge.type ?? "RELATED"}-${target}-${index}`,
        source,
        target,
        label: asString(edge.type) ?? "RELATED_TO",
        strength: asNumber(edge.properties?.similarity_score) ?? 0.78,
      } satisfies DemoMemoryEdge;
    })
    .filter((edge): edge is DemoMemoryEdge => Boolean(edge))
    .filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));

  return { nodes, edges };
}
