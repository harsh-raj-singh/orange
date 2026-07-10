import type { DemoMemoryEdge, DemoMemoryNode, DemoMemoryNodeType } from "@/lib/demo-memory-graph";

type BackendNode = {
  [key: string]: unknown;
  id?: unknown;
  label?: unknown;
  labels?: unknown;
  type?: unknown;
  kind?: unknown;
  node_type?: unknown;
  data?: Record<string, unknown>;
  properties?: Record<string, unknown>;
};

type BackendEdge = {
  [key: string]: unknown;
  id?: unknown;
  source?: unknown;
  target?: unknown;
  source_id?: unknown;
  target_id?: unknown;
  source_insight_id?: unknown;
  target_insight_id?: unknown;
  type?: unknown;
  label?: unknown;
  relationship?: unknown;
  relationship_type?: unknown;
  strength?: unknown;
  similarity_score?: unknown;
  data?: Record<string, unknown>;
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

function asId(value: unknown) {
  if (typeof value === "string") {
    return value;
  }
  return typeof value === "number" && Number.isFinite(value) ? String(value) : undefined;
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
  const normalized = label?.trim().toLowerCase();
  const nodeTypes: Record<string, DemoMemoryNodeType> = {
    problem: "Problem",
    insight: "Insight",
    solution: "Solution",
    attempt: "Attempt",
    artifact: "Artifact",
    concept: "Concept",
    session: "Session",
  };
  if (normalized && normalized in nodeTypes) {
    return nodeTypes[normalized];
  }
  return "Concept";
}

function nodeFields(node: BackendNode) {
  const { data, properties, ...topLevel } = node;
  return {
    ...(data ?? {}),
    ...(properties ?? {}),
    ...topLevel,
  };
}

function backendNodeType(node: BackendNode) {
  const properties = nodeFields(node);
  const labels = Array.isArray(node.labels)
    ? node.labels.find((value): value is string => typeof value === "string")
    : undefined;
  const candidates = [
    asString(node.node_type) ??
      asString(node.kind) ??
      asString(node.type),
    asString(properties.node_type) ??
      asString(properties.kind) ??
      asString(properties.type),
    labels ??
      asString(node.label),
  ].filter((value): value is string => Boolean(value));
  const recognized = candidates.find((candidate) => {
    const normalized = candidate.trim().toLowerCase();
    return nodeTypeFor(candidate) !== "Concept" || normalized === "concept";
  });
  if (recognized) {
    return recognized;
  }
  if (properties.memory_kind || properties.memoryKind || properties.insight_id) {
    return "Insight";
  }
  return candidates[0] ?? "Concept";
}

function isIdentityLike(node: BackendNode) {
  const properties = nodeFields(node);
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

function memoryKindFor(value: unknown) {
  const normalized = asString(value)?.trim().toLowerCase();
  return normalized === "technical_insight" ||
    normalized === "user_fact" ||
    normalized === "company_fact" ||
    normalized === "preference" ||
    normalized === "steering"
    ? normalized
    : undefined;
}

function scopeFor(properties: Record<string, unknown>, fallback: MemoryScope) {
  const rawScope =
    asString(properties.scope) ??
    asString(properties.visibility) ??
    asString(properties.memory_scope);
  const normalized = rawScope?.trim().toLowerCase();

  if (normalized === "global" || normalized === "shared" || normalized === "company") {
    return "global";
  }

  if (normalized === "user" || normalized === "private" || normalized === "personal") {
    return "user";
  }

  return fallback === "global" ? "global" : "user";
}

export function transformBackendGraph(graph: BackendGraph, requestedScope: MemoryScope = "both") {
  const nodes = (graph.nodes ?? [])
    .filter((node) => !isIdentityLike(node))
    .map((node): DemoMemoryNode | null => {
      const properties = nodeFields(node);
      const id =
        asId(node.id) ??
        asId(properties.id) ??
        asId(properties.insight_id) ??
        asId(properties.session_id);
      if (!id) {
        return null;
      }
      const nodeType = nodeTypeFor(backendNodeType(node));
      const scope = scopeFor(properties, requestedScope);
      const legacyLabel = asString(node.label);
      const displayLabelFromNode =
        legacyLabel && nodeTypeFor(legacyLabel) === "Concept" && legacyLabel.toLowerCase() !== "concept"
          ? legacyLabel
          : undefined;
      const label =
        asString(properties.display_label) ??
        asString(properties.displayLabel) ??
        asString(properties.canonical_label) ??
        asString(properties.canonicalLabel) ??
        asString(properties.title) ??
        asString(properties.locator) ??
        displayLabelFromNode ??
        id;
      const summary =
        asString(properties.display_summary) ??
        asString(properties.displaySummary) ??
        asString(properties.description) ??
        asString(properties.in_depth_summary) ??
        asString(properties.inDepthSummary) ??
        asString(properties.summary) ??
        asString(properties.context_brief) ??
        asString(properties.contextBrief) ??
        "Stored Orange memory.";
      const rawDescription =
        asString(properties.raw_description) ??
        asString(properties.rawDescription) ??
        asString(properties.what) ??
        asString(properties.description) ??
        asString(properties.in_depth_summary) ??
        asString(properties.inDepthSummary);
      const outcome = asString(properties.outcome);
      const tags = asStringArray(properties.tags);

      return {
        id,
        label: compactText(label, 72),
        type: nodeType,
        summary: compactText(summary, 220),
        score: asNumber(properties.score) ?? 0.9,
        metadata: {
          owner:
            asString(properties.user_id) ??
            asString(properties.userId) ??
            asString(properties.user_email) ??
            asString(properties.userEmail) ??
            asString(properties.org_id) ??
            asString(properties.organization_id),
          repo: asString(properties.source) ?? asString(properties.repo) ?? "orange-memory",
          createdAt:
            asString(properties.created_at) ??
            asString(properties.createdAt) ??
            asString(properties.ingested_at) ??
            asString(properties.ingestedAt) ??
            asString(properties.updated_at) ??
            asString(properties.updatedAt) ??
            new Date().toISOString(),
          status:
            asString(properties.status) === "open" ||
            asString(properties.status) === "resolved" ||
            asString(properties.status) === "failed" ||
            asString(properties.status) === "active"
              ? (asString(properties.status) as DemoMemoryNode["metadata"]["status"])
              : statusFor(nodeType),
          outcome:
            outcome === "resolved" || outcome === "exploratory" || outcome === "partial" || outcome === "abandoned"
              ? outcome
              : undefined,
          tags,
          memoryKind: memoryKindFor(properties.memory_kind ?? properties.memoryKind),
          scope,
        },
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
    .map((edge) => {
      const properties = { ...(edge.data ?? {}), ...(edge.properties ?? {}) };
      const source =
        asId(edge.source) ??
        asId(edge.source_id) ??
        asId(edge.source_insight_id) ??
        asId(properties.source_id) ??
        asId(properties.source_insight_id);
      const target =
        asId(edge.target) ??
        asId(edge.target_id) ??
        asId(edge.target_insight_id) ??
        asId(properties.target_id) ??
        asId(properties.target_insight_id);
      if (!source || !target) {
        return null;
      }
      const relationship =
        asString(edge.relationship_type) ??
        asString(edge.relationship) ??
        asString(edge.type) ??
        asString(edge.label) ??
        asString(properties.relationship_type) ??
        asString(properties.relationship) ??
        asString(properties.type) ??
        "RELATED_TO";

      return {
        id: asId(edge.id) ?? asId(properties.id) ?? `${source}-${relationship}-${target}`,
        source,
        target,
        label: relationship,
        strength:
          asNumber(edge.similarity_score) ??
          asNumber(edge.strength) ??
          asNumber(properties.similarity_score) ??
          asNumber(properties.strength) ??
          asNumber(properties.weight) ??
          0.78,
      } satisfies DemoMemoryEdge;
    })
    .filter((edge): edge is DemoMemoryEdge => Boolean(edge))
    .filter((edge) => visibleNodeIds.has(edge.source) && visibleNodeIds.has(edge.target));

  return { nodes, edges };
}
