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

function compactText(value: string, maxLength: number) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= maxLength) {
    return text;
  }
  return `${text.slice(0, maxLength - 1).trim()}...`;
}

function statusFor(label?: string): DemoMemoryNode["metadata"]["status"] {
  if (label === "Insight") {
    return "active";
  }
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
    label === "Insight" ||
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

function backendNodeType(node: BackendNode) {
  const properties = node.properties ?? {};
  return (
    asString(properties.node_type) ??
    asString(properties.type) ??
    asString(properties.kind) ??
    asString(node.label) ??
    "Concept"
  );
}

function isIdentityLike(node: BackendNode) {
  const properties = node.properties ?? {};
  const rawType = backendNodeType(node).toLowerCase();
  const knowledgeTypes = new Set(["problem", "solution", "attempt", "artifact", "concept"]);
  knowledgeTypes.add("insight");

  if (rawType === "session" || rawType === "user") {
    return true;
  }

  if (knowledgeTypes.has(rawType)) {
    return false;
  }

  const label = [
    asString(node.label),
    asString(properties.label),
    asString(properties.name),
    asString(properties.email),
    asString(properties.canonical_label),
  ]
    .filter(Boolean)
    .join(" ");

  if (/\b[\w.%+-]+@[\w.-]+\.[a-z]{2,}\b/i.test(label)) {
    return true;
  }

  const name = asString(properties.name) ?? asString(properties.full_name);
  return Boolean(name && !asString(properties.canonical_label) && rawType !== "concept");
}

function asStringArray(value: unknown) {
  if (Array.isArray(value)) {
    return value.filter((item): item is string => typeof item === "string");
  }
  if (typeof value === "string") {
    return value
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  }
  return undefined;
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
    .filter((node) => !isIdentityLike(node))
    .map((node): DemoMemoryNode | null => {
      const id = asString(node.id);
      if (!id) {
        return null;
      }
      const properties = node.properties ?? {};
      const nodeType = nodeTypeFor(backendNodeType(node));
      const scope = scopeFor(properties, requestedScope);
      const label =
        asString(properties.display_label) ??
        asString(properties.canonical_label) ??
        asString(properties.title) ??
        asString(properties.locator) ??
        id;
      const summary =
        asString(properties.display_summary) ??
        asString(properties.description) ??
        asString(properties.in_depth_summary) ??
        asString(properties.summary) ??
        asString(properties.context_brief) ??
        "Stored Orange memory.";
      const rawDescription =
        asString(properties.raw_description) ??
        asString(properties.what) ??
        asString(properties.description) ??
        asString(properties.in_depth_summary);
      const outcome = asString(properties.outcome);
      const tags = asStringArray(properties.tags);

      return {
        id,
        label: compactText(label, 72),
        type: nodeType,
        summary: compactText(summary, 220),
        score: asNumber(properties.score) ?? 0.9,
        metadata: {
          owner: asString(properties.user_id) ?? asString(properties.org_id),
          repo: asString(properties.source) ?? "orange-backend",
          createdAt:
            asString(properties.created_at) ??
            asString(properties.ingested_at) ??
            new Date().toISOString(),
          status: statusFor(nodeType),
          outcome:
            outcome === "resolved" || outcome === "exploratory" || outcome === "partial" || outcome === "abandoned"
              ? outcome
              : undefined,
          tags,
          scope,
        } as DemoMemoryNode["metadata"] & { scope: Exclude<MemoryScope, "both"> },
        detail: rawDescription
          ? {
              title: compactText(label, 72),
              body: compactText(summary, 220),
              fullContext: rawDescription,
              what: asString(properties.what),
              why: asString(properties.why) ?? null,
              how: asString(properties.how) ?? null,
              outcome,
              tags,
            }
          : undefined,
      } as DemoMemoryNode & {
        detail?: {
          title?: string;
          body?: string;
          fullContext?: string;
        };
      };
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
