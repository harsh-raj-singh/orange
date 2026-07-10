"use client";

import dagre from "dagre";
import {
  Background,
  BackgroundVariant,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
  useReactFlow,
  type Edge,
  type Node,
  type NodeProps,
} from "@xyflow/react";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type MemoryScopeValue = "user" | "global";
type MemoryScopeFilter = MemoryScopeValue | "both";
type InsightOutcomeValue = "resolved" | "exploratory" | "partial" | "abandoned";
type MemoryKind =
  | "technical_insight"
  | "user_fact"
  | "company_fact"
  | "preference"
  | "steering"
  | "unknown";

type MemoryNode = {
  id: string;
  label: string;
  kind: "Insight" | "Problem" | "Attempt" | "Solution" | "Artifact" | "Concept" | "Session";
  x: number;
  y: number;
  summary: string;
  score?: number;
  metadata?: {
    owner?: string;
    repo?: string;
    createdAt?: string;
    status?: string;
    scope?: MemoryScopeValue;
    outcome?: InsightOutcomeValue;
    tags?: string[];
    memoryKind?: MemoryKind;
  };
  detailTitle?: string;
  detailBody?: string;
  rawContext?: string;
  what?: string;
  why?: string | null;
  how?: string | null;
  outcome?: InsightOutcomeValue;
  tags?: string[];
  evidence?: string[];
  relatedFiles?: string[];
  nextActions?: string[];
};

type MemoryEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;
  strength?: number;
};

type StoredPosition = { x: number; y: number };
type MemoryFlowNode = Node<MemoryNode & { isNew?: boolean }, "memoryCard">;
type MemoryFlowEdge = Edge<{ strength?: number; related?: boolean }>;
type GraphSyncState = "live" | "stale" | "preview";

const NODE_WIDTH = 228;
const NODE_HEIGHT = 148;
const STORAGE_PREFIX = "orange-memory-graph-positions:v2";
const LIVE_POLL_INTERVAL_MS = 5_000;
const RECOVERY_POLL_INTERVAL_MS = 15_000;

const memoryNodes: MemoryNode[] = [
  {
    id: "cors-insight",
    label: "FastAPI CORS middleware order",
    kind: "Insight",
    x: 18,
    y: 28,
    summary: "OPTIONS requests returned 405 because CORS middleware was registered after routes.",
    detailBody: "A later agent can retrieve the ordering decision before changing origin lists again.",
    what: "FastAPI CORS preflight returned 405 after router setup changed.",
    why: "CORSMiddleware was mounted after route registration.",
    how: "Move CORSMiddleware before include_router.",
    outcome: "resolved",
    tags: ["fastapi", "cors", "middleware-order"],
    metadata: {
      owner: "harsh@example.com",
      repo: "orange-backend",
      status: "active",
      scope: "user",
      outcome: "resolved",
      tags: ["fastapi", "cors", "middleware-order"],
      memoryKind: "technical_insight",
    },
  },
  {
    id: "spain-gtm",
    label: "Spain GTM decision context",
    kind: "Insight",
    x: 43,
    y: 18,
    summary: "Slack decision context is stored as company memory without exposing private attribution.",
    detailBody: "Orange can answer what the team decided weeks later by connecting chat fragments to a company-scoped insight.",
    what: "Team asked what was decided with Rohan about GTM in Spain.",
    why: "Important go-to-market decisions live in chat and disappear from working memory.",
    how: "Store the decision as company-scoped memory retrievable from Slack-like questions.",
    outcome: "exploratory",
    tags: ["slack", "gtm", "company-memory"],
    metadata: {
      owner: "Orange",
      repo: "company-memory",
      status: "active",
      scope: "global",
      outcome: "exploratory",
      tags: ["slack", "gtm", "company-memory"],
      memoryKind: "company_fact",
    },
  },
  {
    id: "markdown-memory",
    label: "Company uses Markdown memory",
    kind: "Insight",
    x: 28,
    y: 62,
    summary: "Company knowledge often lives in Markdown files, so Orange should preserve those facts as scoped memory.",
    detailBody: "This is a company-level fact that helps future agents understand where durable documentation already lives.",
    what: "Company uses .md files for memory.",
    why: "Agents should look for Markdown knowledge before inventing new documentation patterns.",
    how: "Store as company-scoped fact and connect related docs or sessions.",
    outcome: "resolved",
    tags: ["markdown", "company-fact", "docs"],
    metadata: {
      owner: "Orange",
      repo: "company-memory",
      status: "active",
      scope: "global",
      outcome: "resolved",
      tags: ["markdown", "company-fact", "docs"],
      memoryKind: "company_fact",
    },
  },
  {
    id: "website-steering",
    label: "Website steering stays private",
    kind: "Insight",
    x: 62,
    y: 48,
    summary: "Website taste and iteration notes should be private user memory, not shared company knowledge.",
    detailBody: "Orange should remember steering chats that tune a website, even when the site itself can be recreated by any model.",
    what: "User corrected the website direction after removing Problem/Solution vocabulary.",
    why: "Design preferences are personal steering, not globally useful technical knowledge.",
    how: "Store as private memory keyed by email.",
    outcome: "resolved",
    tags: ["frontend", "website-steering", "private-memory"],
    metadata: {
      owner: "harsh@example.com",
      repo: "orange-site",
      status: "active",
      scope: "user",
      outcome: "resolved",
      tags: ["frontend", "website-steering", "private-memory"],
      memoryKind: "steering",
    },
  },
  {
    id: "aws-glue-fact",
    label: "AWS Glue incident cause",
    kind: "Insight",
    x: 78,
    y: 22,
    summary: "Global/company memory should keep reusable incident causes like AWS Glue issues.",
    detailBody: "This kind of fact helps coworkers facing the same infrastructure symptom inside the same company graph.",
    what: "An error happened because of an AWS Glue issue.",
    why: "Cloud service behavior can be the real cause, not application code.",
    how: "Store the incident cause as company-scoped shared memory.",
    outcome: "partial",
    tags: ["aws-glue", "incident", "company-memory"],
    metadata: {
      owner: "Orange",
      repo: "company-memory",
      status: "active",
      scope: "global",
      outcome: "partial",
      tags: ["aws-glue", "incident", "company-memory"],
      memoryKind: "technical_insight",
    },
  },
];

const fallbackEdges: MemoryEdge[] = [
  { id: "cors-steering", source: "cors-insight", target: "website-steering", label: "SIMILAR_TO", strength: 0.68 },
  { id: "spain-markdown", source: "spain-gtm", target: "markdown-memory", label: "SIMILAR_TO", strength: 0.72 },
  { id: "spain-aws", source: "spain-gtm", target: "aws-glue-fact", label: "shared", strength: 0.58 },
  { id: "markdown-aws", source: "markdown-memory", target: "aws-glue-fact", label: "facts", strength: 0.64 },
];

const visibleMemoryNodes = memoryNodes.filter((node) => node.kind !== "Session");
const visibleMemoryNodeIds = new Set(visibleMemoryNodes.map((node) => node.id));
const visibleFallbackEdges = fallbackEdges.filter(
  (edge) => visibleMemoryNodeIds.has(edge.source) && visibleMemoryNodeIds.has(edge.target),
);
const initialScope: MemoryScopeValue = "global";
const initialMemoryNodes = visibleMemoryNodes.filter((node) => nodeScope(node) === initialScope);
const initialMemoryNodeIds = new Set(initialMemoryNodes.map((node) => node.id));
const initialMemoryEdges = visibleFallbackEdges.filter(
  (edge) => initialMemoryNodeIds.has(edge.source) && initialMemoryNodeIds.has(edge.target),
);

const scopeOptions: ReadonlyArray<{ value: MemoryScopeFilter; label: string }> = [
  { value: "global", label: "Shared workspace" },
  { value: "user", label: "My private notes" },
];

const memoryKindStyles: Record<MemoryKind, { accent: string; bg: string; border: string; text: string }> = {
  technical_insight: { accent: "#2f7f78", bg: "#eefbf8", border: "#9ed6cc", text: "#1f5d58" },
  preference: { accent: "#9a5c16", bg: "#fff8ec", border: "#efc985", text: "#7a430c" },
  steering: { accent: "#c5551c", bg: "#fff3e8", border: "#f0b17f", text: "#8f3b14" },
  company_fact: { accent: "#55479a", bg: "#f5f2ff", border: "#b9afe9", text: "#40347f" },
  user_fact: { accent: "#2f6f5e", bg: "#f1faf5", border: "#a9d8c7", text: "#205545" },
  unknown: { accent: "#5f746b", bg: "#f7f9f6", border: "#cdd6ce", text: "#344740" },
};

const outcomeClass: Record<InsightOutcomeValue, string> = {
  resolved: "bg-[#f1faf5] text-[#2f6f5e]",
  exploratory: "bg-[#eef6ff] text-[#2f5f8f]",
  partial: "bg-[#fff8ec] text-[#9a5c16]",
  abandoned: "bg-[#f3f4f2] text-[#5f6a64]",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : undefined;
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

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
}

function normalizeScope(value: unknown): MemoryScopeValue {
  const normalized = asString(value)?.trim().toLowerCase();
  return normalized === "global" || normalized === "shared" || normalized === "company" ? "global" : "user";
}

function normalizeOutcome(value: unknown): InsightOutcomeValue | undefined {
  const normalized = asString(value)?.trim().toLowerCase();
  return normalized === "resolved" ||
    normalized === "exploratory" ||
    normalized === "partial" ||
    normalized === "abandoned"
    ? normalized
    : undefined;
}

function normalizeMemoryKind(value: unknown): MemoryKind {
  const normalized = asString(value)?.trim().toLowerCase();
  return normalized === "technical_insight" ||
    normalized === "user_fact" ||
    normalized === "company_fact" ||
    normalized === "preference" ||
    normalized === "steering"
    ? normalized
    : "unknown";
}

function normalizeKind(value: unknown): MemoryNode["kind"] {
  const kind = asString(value)?.trim().toLowerCase();
  const kinds: Record<string, MemoryNode["kind"]> = {
    insight: "Insight",
    problem: "Problem",
    attempt: "Attempt",
    solution: "Solution",
    artifact: "Artifact",
    concept: "Concept",
    session: "Session",
  };
  return kind ? (kinds[kind] ?? "Concept") : "Concept";
}

function graphContextKey(scope: MemoryScopeFilter, userEmail: string, company: string) {
  const userPart = scope === "global" ? "" : userEmail.trim().toLowerCase();
  const companyPart = scope === "user" ? "" : company.trim().toLowerCase();
  return `${scope}:${userPart}:${companyPart}`;
}

function graphSearchParams(scope: MemoryScopeFilter, userEmail: string, company: string) {
  const params = new URLSearchParams({ scope });
  if (scope !== "global" && userEmail) {
    params.set("user_email", userEmail);
  }
  if (scope !== "user" && company) {
    params.set("company", company);
  }
  return params;
}

function isAbortError(error: unknown) {
  return error instanceof DOMException && error.name === "AbortError";
}

function truncateLabel(value: string, maxLength = 36) {
  return value.length <= maxLength ? value : `${value.slice(0, maxLength - 1).trim()}...`;
}

function nodeScope(node?: MemoryNode): MemoryScopeValue {
  return node?.metadata?.scope ?? "user";
}

function nodeMemoryKind(node?: MemoryNode): MemoryKind {
  return normalizeMemoryKind(node?.metadata?.memoryKind);
}

function normalizeNode(value: unknown, existing?: MemoryNode): MemoryNode | null {
  if (!isRecord(value)) {
    return null;
  }

  const id = asString(value.id);

  if (!id) {
    return null;
  }

  const detail = isRecord(value.detail) ? value.detail : undefined;
  const metadata = isRecord(value.metadata)
    ? {
        owner:
          asString(value.metadata.owner) ??
          asString(value.metadata.user_id) ??
          asString(value.metadata.user_email) ??
          asString(value.metadata.org_id),
        repo: asString(value.metadata.repo) ?? asString(value.metadata.source),
        createdAt: asString(value.metadata.createdAt) ?? asString(value.metadata.created_at),
        status: asString(value.metadata.status),
        scope: normalizeScope(value.metadata.scope ?? value.metadata.visibility),
        outcome: normalizeOutcome(value.metadata.outcome),
        tags: asStringArray(value.metadata.tags),
        memoryKind: normalizeMemoryKind(value.metadata.memoryKind ?? value.metadata.memory_kind),
      }
    : existing?.metadata;
  const detailBody = asString(value.detail) ?? asString(detail?.body) ?? existing?.detailBody;
  const rawContext = asString(detail?.fullContext) ?? asString(detail?.rawDescription) ?? existing?.rawContext;
  const tags = asStringArray(detail?.tags) ?? metadata?.tags ?? existing?.tags;
  const outcome = normalizeOutcome(detail?.outcome) ?? metadata?.outcome ?? existing?.outcome;
  const x = asNumber(value.x) ?? existing?.x ?? 50;
  const y = asNumber(value.y) ?? existing?.y ?? 50;

  return {
    id,
    label: asString(value.label) ?? asString(value.display_label) ?? existing?.label ?? "Untitled memory",
    kind: normalizeKind(value.kind ?? value.type ?? existing?.kind),
    x,
    y,
    summary:
      asString(value.summary) ??
      asString(value.display_summary) ??
      existing?.summary ??
      "New memory node waiting for context.",
    score: asNumber(value.score) ?? existing?.score,
    metadata,
    detailTitle: asString(detail?.title) ?? existing?.detailTitle,
    detailBody,
    rawContext,
    what: asString(detail?.what) ?? existing?.what,
    why: asString(detail?.why) ?? existing?.why,
    how: asString(detail?.how) ?? existing?.how,
    outcome,
    tags,
    evidence: asStringArray(detail?.evidence) ?? existing?.evidence,
    relatedFiles: asStringArray(detail?.relatedFiles) ?? existing?.relatedFiles,
    nextActions: asStringArray(detail?.nextActions) ?? existing?.nextActions,
  };
}

function normalizeEdge(value: unknown): MemoryEdge | null {
  if (!isRecord(value)) {
    return null;
  }

  const source = asString(value.source) ?? asString(value.from);
  const target = asString(value.target) ?? asString(value.to);

  if (!source || !target) {
    return null;
  }

  return {
    id: asString(value.id) ?? `${source}-${target}`,
    source,
    target,
    label: asString(value.label) ?? asString(value.type) ?? asString(value.relationship),
    strength: asNumber(value.strength) ?? asNumber(value.similarity_score),
  };
}

function isSimilarEdge(edge: MemoryEdge) {
  return edge.label?.toUpperCase() === "SIMILAR_TO";
}

function edgeLabel(edge: MemoryEdge) {
  if (isSimilarEdge(edge)) {
    return `SIMILAR_TO ${((edge.strength ?? 0) * 100).toFixed(0)}%`;
  }
  return edge.label;
}

function formatDate(value?: string) {
  if (!value) {
    return undefined;
  }

  const date = new Date(value);

  if (Number.isNaN(date.getTime())) {
    return undefined;
  }

  return new Intl.DateTimeFormat("en", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function storageKey(scope: MemoryScopeFilter) {
  return `${STORAGE_PREFIX}:${scope}`;
}

function readStoredPositions(scope: MemoryScopeFilter): Record<string, StoredPosition> {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(storageKey(scope));
    const parsed = raw ? (JSON.parse(raw) as Record<string, StoredPosition>) : {};
    return Object.fromEntries(
      Object.entries(parsed).filter(
        ([, position]) =>
          Number.isFinite(position?.x) &&
          Number.isFinite(position?.y),
      ),
    );
  } catch {
    return {};
  }
}

function writeStoredPositions(scope: MemoryScopeFilter, positions: Record<string, StoredPosition>) {
  try {
    window.localStorage.setItem(storageKey(scope), JSON.stringify(positions));
  } catch {
    // Position persistence is a convenience; graph interaction should continue without it.
  }
}

function clearStoredPositions(scope: MemoryScopeFilter) {
  try {
    window.localStorage.removeItem(storageKey(scope));
  } catch {
    // The graph can still be re-laid out when browser storage is unavailable.
  }
}

function positionsEqual(left: Record<string, StoredPosition>, right: Record<string, StoredPosition>) {
  const leftEntries = Object.entries(left);
  const rightEntries = Object.entries(right);

  if (leftEntries.length !== rightEntries.length) {
    return false;
  }

  return leftEntries.every(([id, position]) => {
    const other = right[id];
    return other && other.x === position.x && other.y === position.y;
  });
}

function graphHydrationSignature(
  nodes: MemoryNode[],
  edges: MemoryEdge[],
  scope: MemoryScopeFilter,
) {
  return JSON.stringify({
    scope,
    nodes: nodes.map((node) => [
      node.id,
      node.kind,
      node.label,
      node.summary,
      nodeScope(node),
      nodeMemoryKind(node),
      node.metadata?.status,
      node.outcome,
      node.score,
      node.what,
      node.why,
      node.how,
      node.tags?.join("|"),
    ]),
    edges: edges.map((edge) => [edge.id, edge.source, edge.target, edge.label, edge.strength]),
  });
}

function layoutNodes(
  memoryNodesInput: MemoryNode[],
  memoryEdgesInput: MemoryEdge[],
  storedPositions: Record<string, StoredPosition>,
  newNodeIds: Set<string>,
): MemoryFlowNode[] {
  const graph = new dagre.graphlib.Graph();
  graph.setDefaultEdgeLabel(() => ({}));
  graph.setGraph({ rankdir: "LR", nodesep: 82, ranksep: 150, marginx: 64, marginy: 64 });

  memoryNodesInput.forEach((node) => {
    graph.setNode(node.id, { width: NODE_WIDTH, height: NODE_HEIGHT });
  });
  memoryEdgesInput
    .filter((edge) => !isSimilarEdge(edge))
    .forEach((edge) => {
      graph.setEdge(edge.source, edge.target);
    });

  dagre.layout(graph);

  const positions = new Map<string, StoredPosition>();
  memoryNodesInput.forEach((node) => {
    const stored = storedPositions[node.id];
    const dagreNode = graph.node(node.id);
    positions.set(
      node.id,
      stored ?? {
        x: dagreNode ? dagreNode.x - NODE_WIDTH / 2 : node.x * 8,
        y: dagreNode ? dagreNode.y - NODE_HEIGHT / 2 : node.y * 5,
      },
    );
  });

  const similarGroups = findSimilarGroups(memoryNodesInput, memoryEdgesInput);
  similarGroups.forEach((group) => {
    const movable = group.filter((id) => !storedPositions[id]);
    if (movable.length < 2) {
      return;
    }

    const centroid = movable.reduce(
      (total, id) => {
        const position = positions.get(id) ?? { x: 0, y: 0 };
        return { x: total.x + position.x, y: total.y + position.y };
      },
      { x: 0, y: 0 },
    );
    centroid.x /= movable.length;
    centroid.y /= movable.length;

    const radius = Math.max(132, movable.length * 30);
    movable.forEach((id, index) => {
      const angle = (index / movable.length) * Math.PI * 2;
      positions.set(id, {
        x: centroid.x + Math.cos(angle) * radius,
        y: centroid.y + Math.sin(angle) * radius * 0.78,
      });
    });
  });

  return memoryNodesInput.map((node) => ({
    id: node.id,
    type: "memoryCard",
    position: positions.get(node.id) ?? { x: node.x * 8, y: node.y * 5 },
    data: { ...node, isNew: newNodeIds.has(node.id) },
  }));
}

function findSimilarGroups(nodes: MemoryNode[], edges: MemoryEdge[]) {
  const nodeIds = new Set(nodes.map((node) => node.id));
  const adjacency = new Map<string, Set<string>>();
  edges.filter(isSimilarEdge).forEach((edge) => {
    if (!nodeIds.has(edge.source) || !nodeIds.has(edge.target)) {
      return;
    }
    adjacency.set(edge.source, (adjacency.get(edge.source) ?? new Set()).add(edge.target));
    adjacency.set(edge.target, (adjacency.get(edge.target) ?? new Set()).add(edge.source));
  });

  const visited = new Set<string>();
  const groups: string[][] = [];
  adjacency.forEach((_neighbors, start) => {
    if (visited.has(start)) {
      return;
    }
    const group: string[] = [];
    const stack = [start];
    visited.add(start);
    while (stack.length) {
      const current = stack.pop();
      if (!current) {
        continue;
      }
      group.push(current);
      adjacency.get(current)?.forEach((next) => {
        if (!visited.has(next)) {
          visited.add(next);
          stack.push(next);
        }
      });
    }
    if (group.length > 1) {
      groups.push(group);
    }
  });
  return groups;
}

function layoutEdges(memoryEdgesInput: MemoryEdge[]): MemoryFlowEdge[] {
  return memoryEdgesInput.map((edge) => {
    const related = isSimilarEdge(edge);
    return {
      id: edge.id,
      source: edge.source,
      target: edge.target,
      label: edgeLabel(edge),
      type: "default",
      data: { strength: edge.strength, related },
      markerEnd: related ? undefined : { type: MarkerType.ArrowClosed, color: "#9aa79d" },
      labelBgBorderRadius: 5,
      labelBgPadding: [6, 3],
      labelStyle: { fill: "#617067", fontSize: 10, fontWeight: 700, letterSpacing: 0.4 },
      labelBgStyle: { fill: "#f8faf7", fillOpacity: 0.94 },
      style: {
        stroke: related ? "#c7926c" : "#7c9d8d",
        strokeDasharray: related ? "6 7" : undefined,
        strokeOpacity: related ? 0.7 : 0.5 + (edge.strength ?? 0.7) * 0.22,
        strokeWidth: related ? 1.7 : 1.4 + (edge.strength ?? 0.7),
      },
    };
  });
}

function MemoryCardNode({ data, selected }: NodeProps<MemoryFlowNode>) {
  const memoryKind = nodeMemoryKind(data);
  const style = memoryKindStyles[memoryKind];
  const scope = nodeScope(data);
  const capturedAt = formatDate(data.metadata?.createdAt);

  return (
    <button
      type="button"
      className={`memory-card group relative flex h-[9.25rem] w-[14.25rem] flex-col overflow-hidden rounded-xl border text-left transition ${
        selected ? "is-selected" : "hover:-translate-y-1"
      } ${data.isNew ? "animate-[node-pop_520ms_ease_forwards]" : ""}`}
      style={{ borderColor: style.border, color: style.text, "--memory-accent": style.accent } as React.CSSProperties}
    >
      <span className="absolute inset-x-0 top-0 h-1" style={{ background: style.accent }} aria-hidden="true" />
      <Handle type="target" position={Position.Left} className="!h-2.5 !w-2.5 !border-2 !border-white" style={{ background: style.accent }} />
      <span className="flex items-center justify-between gap-2 px-4 pt-4">
        <span className="flex items-center gap-2 font-mono text-[0.63rem] font-bold uppercase tracking-[0.13em]">
          <span className="h-1.5 w-1.5 rounded-full" style={{ background: style.accent }} aria-hidden="true" />
          {memoryKind.replaceAll("_", " ")}
        </span>
        <span className={`rounded-full px-2 py-0.5 font-mono text-[0.58rem] font-bold uppercase tracking-[0.1em] ${
          scope === "global" ? "bg-[#eee9ff] text-[#55479a]" : "bg-[#fff0e5] text-[#a44719]"
        }`}>
          {scope === "global" ? "shared" : "private"}
        </span>
      </span>
      <span className="mt-2 block px-4 text-[0.92rem] font-bold leading-5 text-[#172019]">{truncateLabel(data.label, 44)}</span>
      <span className="mt-1.5 line-clamp-2 block px-4 text-[0.7rem] leading-[1.1rem] text-[#59665f]">{data.summary}</span>
      <span className="mt-auto flex items-center justify-between border-t border-[#24352d]/8 px-4 py-2 font-mono text-[0.58rem] font-semibold uppercase tracking-[0.1em] text-[#77837c]">
        <span>{data.outcome ?? data.metadata?.status ?? data.kind}</span>
        <span>{capturedAt ?? "Orange memory"}</span>
      </span>
      <Handle type="source" position={Position.Right} className="!h-2.5 !w-2.5 !border-2 !border-white" style={{ background: style.accent }} />
    </button>
  );
}

const nodeTypes = { memoryCard: MemoryCardNode };

export default function MemoryGraph() {
  return (
    <ReactFlowProvider>
      <MemoryGraphInner />
    </ReactFlowProvider>
  );
}

function MemoryGraphInner() {
  const { fitView } = useReactFlow<MemoryFlowNode, MemoryFlowEdge>();
  const [memoryNodeList, setMemoryNodeList] = useState(initialMemoryNodes);
  const [memoryEdgeList, setMemoryEdgeList] = useState<MemoryEdge[]>(initialMemoryEdges);
  const [selectedId, setSelectedId] = useState(initialMemoryNodes[0]?.id ?? "");
  const [scope, setScope] = useState<MemoryScopeFilter>(initialScope);
  const [nodePositions, setNodePositions] = useState<Record<string, StoredPosition>>(() => readStoredPositions(initialScope));
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<MemoryFlowNode>(
    layoutNodes(initialMemoryNodes, initialMemoryEdges, readStoredPositions(initialScope), new Set()),
  );
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [graphSyncState, setGraphSyncState] = useState<GraphSyncState>("preview");
  const [hasLoadedGraph, setHasLoadedGraph] = useState(false);
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);
  const [introVisible, setIntroVisible] = useState(false);
  const [userEmail, setUserEmail] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    try {
      const storedProfile = window.localStorage.getItem("orange-demo-profile");
      if (!storedProfile) {
        return "";
      }
      const parsed = JSON.parse(storedProfile) as { email?: unknown };
      return typeof parsed.email === "string" ? parsed.email.trim().toLowerCase() : "";
    } catch {
      return "";
    }
  });
  const [company, setCompany] = useState(() => {
    if (typeof window === "undefined") {
      return "";
    }
    try {
      const storedProfile = window.localStorage.getItem("orange-demo-profile");
      if (!storedProfile) {
        return "";
      }
      const parsed = JSON.parse(storedProfile) as { company?: unknown };
      return typeof parsed.company === "string" ? parsed.company.trim() : "";
    } catch {
      return "";
    }
  });
  const currentGraphContext = graphContextKey(scope, userEmail, company);
  const currentGraphQuery = graphSearchParams(scope, userEmail, company).toString();
  const graphRef = useRef<HTMLDivElement>(null);
  const memoryNodeListRef = useRef(initialMemoryNodes);
  const memoryEdgeListRef = useRef<MemoryEdge[]>(initialMemoryEdges);
  const flowNodesRef = useRef(flowNodes);
  const activeGraphContextRef = useRef(currentGraphContext);
  const renderedGraphContextRef = useRef(currentGraphContext);
  const seenNodeIdsByContextRef = useRef(new Map<string, Set<string>>());
  const liveSnapshotContextsRef = useRef(new Set<string>());
  const liveGraphSnapshotsRef = useRef(
    new Map<string, { nodes: MemoryNode[]; edges: MemoryEdge[] }>(),
  );
  const graphVersionsByContextRef = useRef(new Map<string, string>());
  const graphFetchControllerRef = useRef<AbortController | null>(null);
  const versionFetchControllerRef = useRef<AbortController | null>(null);
  const detailFetchControllerRef = useRef<AbortController | null>(null);
  const graphFetchSequenceRef = useRef(0);
  const isGraphVisibleRef = useRef(false);
  const hasRevealedGraphRef = useRef(false);
  const isDraggingRef = useRef(false);
  const nextFallbackPollAtRef = useRef(0);
  const isVersionCheckInFlightRef = useRef(false);
  const lastHydratedSignatureRef = useRef(
    graphHydrationSignature(initialMemoryNodes, initialMemoryEdges, initialScope),
  );

  const selectedNode = useMemo(
    () => memoryNodeList.find((node) => node.id === selectedId) ?? memoryNodeList[0],
    [memoryNodeList, selectedId],
  );
  const selectedDate = formatDate(selectedNode?.metadata?.createdAt);
  const selectedScope = nodeScope(selectedNode);
  const flowEdges = useMemo(() => layoutEdges(memoryEdgeList), [memoryEdgeList]);

  const persistFlowPositions = useCallback(
    (nodesToPersist: MemoryFlowNode[]) => {
      const positions = Object.fromEntries(
        nodesToPersist.map((node) => [node.id, { x: node.position.x, y: node.position.y }]),
      );
      if (positionsEqual(nodePositions, positions)) {
        return;
      }
      writeStoredPositions(scope, positions);
      setNodePositions(positions);
    },
    [nodePositions, scope],
  );

  const fitGraph = useCallback(() => {
    void fitView({ padding: 0.22, duration: 650, maxZoom: 1.12 });
  }, [fitView]);

  const resetGraphLayout = useCallback(() => {
    clearStoredPositions(scope);
    setNodePositions({});
    const nextNodes = layoutNodes(memoryNodeListRef.current, memoryEdgeListRef.current, {}, new Set());
    flowNodesRef.current = nextNodes;
    setFlowNodes(nextNodes);
    window.setTimeout(fitGraph, 40);
  }, [fitGraph, scope, setFlowNodes]);

  const hydrateFlowNodes = useCallback(
    (
      nextNodes: MemoryNode[],
      nextEdges: MemoryEdge[],
      nextScope: MemoryScopeFilter,
      freshIds: Set<string> = new Set(),
      nextGraphContext = currentGraphContext,
    ) => {
      if (isDraggingRef.current) {
        return;
      }
      const signature = `${nextGraphContext}:${graphHydrationSignature(nextNodes, nextEdges, nextScope)}`;
      if (freshIds.size === 0 && lastHydratedSignatureRef.current === signature) {
        return;
      }

      const visibleNodeIds = new Set(nextNodes.map((node) => node.id));
      const currentPositions =
        renderedGraphContextRef.current === nextGraphContext
          ? Object.fromEntries(
              flowNodesRef.current
                .filter((node) => visibleNodeIds.has(node.id))
                .map((node) => [node.id, { x: node.position.x, y: node.position.y }]),
            )
          : {};
      const storedPositions = {
        ...readStoredPositions(nextScope),
        ...currentPositions,
      };
      lastHydratedSignatureRef.current = signature;
      renderedGraphContextRef.current = nextGraphContext;
      setNodePositions(storedPositions);
      setFlowNodes(layoutNodes(nextNodes, nextEdges, storedPositions, freshIds));
      if (freshIds.size > 0 || Object.keys(currentPositions).length === 0) {
        window.setTimeout(fitGraph, 60);
      }
    },
    [currentGraphContext, fitGraph, setFlowNodes],
  );

  useEffect(() => {
    memoryNodeListRef.current = memoryNodeList;
  }, [memoryNodeList]);

  useEffect(() => {
    memoryEdgeListRef.current = memoryEdgeList;
  }, [memoryEdgeList]);

  useEffect(() => {
    flowNodesRef.current = flowNodes;
  }, [flowNodes]);

  useEffect(() => {
    activeGraphContextRef.current = currentGraphContext;
  }, [currentGraphContext]);

  const prepareGraphContext = useCallback(
    (nextScope: MemoryScopeFilter, nextUserEmail: string, nextCompany: string) => {
      const nextContext = graphContextKey(nextScope, nextUserEmail, nextCompany);
      if (nextContext === activeGraphContextRef.current) {
        return;
      }

      activeGraphContextRef.current = nextContext;
      graphFetchSequenceRef.current += 1;
      graphFetchControllerRef.current?.abort();
      versionFetchControllerRef.current?.abort();
      detailFetchControllerRef.current?.abort();
      graphFetchControllerRef.current = null;
      versionFetchControllerRef.current = null;
      detailFetchControllerRef.current = null;
      isVersionCheckInFlightRef.current = false;
      nextFallbackPollAtRef.current = 0;
      isDraggingRef.current = false;

      const cachedSnapshot = liveGraphSnapshotsRef.current.get(nextContext);
      if (cachedSnapshot) {
        memoryNodeListRef.current = cachedSnapshot.nodes;
        memoryEdgeListRef.current = cachedSnapshot.edges;
        setMemoryNodeList(cachedSnapshot.nodes);
        setMemoryEdgeList(cachedSnapshot.edges);
        setSelectedId(cachedSnapshot.nodes[0]?.id ?? "");
        setHasLoadedGraph(true);
        setGraphSyncState("stale");
        hydrateFlowNodes(cachedSnapshot.nodes, cachedSnapshot.edges, nextScope, new Set(), nextContext);
      } else {
        memoryNodeListRef.current = [];
        memoryEdgeListRef.current = [];
        flowNodesRef.current = [];
        renderedGraphContextRef.current = nextContext;
        lastHydratedSignatureRef.current = `${nextContext}:${graphHydrationSignature([], [], nextScope)}`;
        setMemoryNodeList([]);
        setMemoryEdgeList([]);
        setFlowNodes([]);
        setNodePositions({});
        setSelectedId("");
        setHasLoadedGraph(false);
        setGraphSyncState("preview");
      }
      setDetailLoadingId(null);
      setIsRefreshing(false);
    },
    [hydrateFlowNodes, setFlowNodes],
  );

  useEffect(() => {
    function handleProfileUpdate() {
      try {
        const storedProfile = window.localStorage.getItem("orange-demo-profile");
        const parsed = storedProfile
          ? (JSON.parse(storedProfile) as { email?: unknown; company?: unknown })
          : {};
        const nextUserEmail = typeof parsed.email === "string" ? parsed.email.trim().toLowerCase() : "";
        const nextCompany = typeof parsed.company === "string" ? parsed.company.trim() : "";
        prepareGraphContext(scope, nextUserEmail, nextCompany);
        setUserEmail(nextUserEmail);
        setCompany(nextCompany);
      } catch {
        prepareGraphContext(scope, "", "");
        setUserEmail("");
        setCompany("");
      }
    }

    window.addEventListener("orange-demo-profile-updated", handleProfileUpdate);
    return () => window.removeEventListener("orange-demo-profile-updated", handleProfileUpdate);
  }, [prepareGraphContext, scope]);

  const fetchGraph = useCallback(async (showRefreshing = true) => {
    const requestContext = currentGraphContext;
    const requestSequence = graphFetchSequenceRef.current + 1;
    graphFetchSequenceRef.current = requestSequence;
    graphFetchControllerRef.current?.abort();
    const controller = new AbortController();
    graphFetchControllerRef.current = controller;

    if (showRefreshing) {
      setIsRefreshing(true);
    }

    try {
      const response = await fetch(`/api/demo/memory-graph?${currentGraphQuery}`, {
        cache: "no-store",
        signal: controller.signal,
      });

      if (!response.ok) {
        throw new Error(`Graph request failed: ${response.status}`);
      }

      const graph: unknown = await response.json();
      if (
        !isRecord(graph) ||
        requestSequence !== graphFetchSequenceRef.current ||
        activeGraphContextRef.current !== requestContext
      ) {
        return;
      }

      const isLiveGraph = graph.source === "backend" || graph.source === "live";
      const hasLiveSnapshot = liveSnapshotContextsRef.current.has(requestContext);
      setHasLoadedGraph(true);

      if (!isLiveGraph && hasLiveSnapshot) {
        nextFallbackPollAtRef.current = Date.now() + RECOVERY_POLL_INTERVAL_MS;
        setGraphSyncState("stale");
        return;
      }

      if (isLiveGraph) {
        liveSnapshotContextsRef.current.add(requestContext);
        nextFallbackPollAtRef.current = Date.now() + RECOVERY_POLL_INTERVAL_MS;
        setGraphSyncState("live");
      } else {
        nextFallbackPollAtRef.current = Date.now() + RECOVERY_POLL_INTERVAL_MS;
        setGraphSyncState("preview");
      }

      const currentMemoryNodes =
        renderedGraphContextRef.current === requestContext ? memoryNodeListRef.current : [];
      const currentMemoryEdges =
        renderedGraphContextRef.current === requestContext ? memoryEdgeListRef.current : [];
      const existingById = new Map(currentMemoryNodes.map((node) => [node.id, node]));
      const apiNodes = Array.isArray(graph.nodes)
        ? graph.nodes
            .map((node) => normalizeNode(node, isRecord(node) ? existingById.get(asString(node.id) ?? "") : undefined))
            .filter((node): node is MemoryNode => Boolean(node))
        : [];
      const fallbackNodes = visibleMemoryNodes.filter((node) => nodeScope(node) === scope);
      const nextMemoryNodes = isLiveGraph ? apiNodes : fallbackNodes;

      let freshIdSet = new Set<string>();
      if (isLiveGraph) {
        const seenIds = seenNodeIdsByContextRef.current.get(requestContext);
        if (seenIds) {
          const freshIds = nextMemoryNodes.map((node) => node.id).filter((id) => !seenIds.has(id));
          freshIds.forEach((id) => seenIds.add(id));
          freshIdSet = new Set(freshIds);
        } else {
          seenNodeIdsByContextRef.current.set(
            requestContext,
            new Set(nextMemoryNodes.map((node) => node.id)),
          );
        }
      }

      if (freshIdSet.size > 0) {
        window.setTimeout(() => {
          setFlowNodes((current) =>
            current.map((node) => ({
              ...node,
              data: { ...node.data, isNew: false },
            })),
          );
        }, 600);
      }

      setSelectedId((current) =>
        nextMemoryNodes.some((node) => node.id === current) ? current : (nextMemoryNodes[0]?.id ?? ""),
      );

      const apiEdges = Array.isArray(graph.edges)
        ? graph.edges.map(normalizeEdge).filter((edge): edge is MemoryEdge => Boolean(edge))
        : [];
      const fallbackNodeIds = new Set(fallbackNodes.map((node) => node.id));
      const fallbackGraphEdges = visibleFallbackEdges.filter(
        (edge) => fallbackNodeIds.has(edge.source) && fallbackNodeIds.has(edge.target),
      );
      const nextMemoryEdges = isLiveGraph ? apiEdges : fallbackGraphEdges;
      if (isLiveGraph) {
        liveGraphSnapshotsRef.current.set(requestContext, {
          nodes: nextMemoryNodes,
          edges: nextMemoryEdges,
        });
      }

      const currentSignature = graphHydrationSignature(currentMemoryNodes, currentMemoryEdges, scope);
      const nextSignature = graphHydrationSignature(nextMemoryNodes, nextMemoryEdges, scope);
      if (currentSignature !== nextSignature) {
        memoryNodeListRef.current = nextMemoryNodes;
        memoryEdgeListRef.current = nextMemoryEdges;
        setMemoryNodeList(nextMemoryNodes);
        setMemoryEdgeList(nextMemoryEdges);
      }
      hydrateFlowNodes(nextMemoryNodes, nextMemoryEdges, scope, freshIdSet, requestContext);
    } catch (error) {
      if (!isAbortError(error)) {
        if (
          requestSequence === graphFetchSequenceRef.current &&
          activeGraphContextRef.current === requestContext
        ) {
          setGraphSyncState(liveSnapshotContextsRef.current.has(requestContext) ? "stale" : "preview");
        }
        console.warn("Unable to refresh memory graph", error);
      }
    } finally {
      if (requestSequence === graphFetchSequenceRef.current) {
        graphFetchControllerRef.current = null;
        if (showRefreshing) {
          setIsRefreshing(false);
        }
      }
    }
  }, [currentGraphContext, currentGraphQuery, hydrateFlowNodes, scope, setFlowNodes]);

  const checkGraphVersion = useCallback(async () => {
    if (isVersionCheckInFlightRef.current) {
      return;
    }
    const requestContext = currentGraphContext;
    const controller = new AbortController();
    versionFetchControllerRef.current?.abort();
    versionFetchControllerRef.current = controller;
    isVersionCheckInFlightRef.current = true;

    try {
      const response = await fetch(`/api/demo/memory-graph/version?${currentGraphQuery}`, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Graph version request failed: ${response.status}`);
      }

      const payload: unknown = await response.json();
      if (activeGraphContextRef.current !== requestContext) {
        return;
      }

      const isLiveVersion =
        isRecord(payload) && (payload.source === "backend" || payload.source === "live");
      const version = isRecord(payload)
        ? typeof payload.version === "string"
          ? payload.version
          : typeof payload.version === "number" && Number.isFinite(payload.version)
            ? String(payload.version)
            : undefined
        : undefined;
      if (!isLiveVersion || !version) {
        if (liveSnapshotContextsRef.current.has(requestContext)) {
          setGraphSyncState("stale");
        }
        if (Date.now() >= nextFallbackPollAtRef.current) {
          nextFallbackPollAtRef.current = Date.now() + RECOVERY_POLL_INTERVAL_MS;
          await fetchGraph(false);
        }
        return;
      }

      const previousVersion = graphVersionsByContextRef.current.get(requestContext);
      graphVersionsByContextRef.current.set(requestContext, version);
      if (!liveSnapshotContextsRef.current.has(requestContext)) {
        await fetchGraph(false);
      } else if (previousVersion && previousVersion !== version) {
        await fetchGraph(false);
      } else {
        setGraphSyncState("live");
      }
    } catch (error) {
      if (!isAbortError(error)) {
        if (
          activeGraphContextRef.current === requestContext &&
          liveSnapshotContextsRef.current.has(requestContext)
        ) {
          setGraphSyncState("stale");
        }
        console.warn("Unable to check memory graph version", error);
        if (
          activeGraphContextRef.current === requestContext &&
          Date.now() >= nextFallbackPollAtRef.current
        ) {
          nextFallbackPollAtRef.current = Date.now() + RECOVERY_POLL_INTERVAL_MS;
          await fetchGraph(false);
        }
      }
    } finally {
      if (versionFetchControllerRef.current === controller) {
        versionFetchControllerRef.current = null;
        isVersionCheckInFlightRef.current = false;
      }
    }
  }, [currentGraphContext, currentGraphQuery, fetchGraph]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => {
      void fetchGraph(false).then(() => checkGraphVersion());
    }, 0);

    const handleGraphUpdate = () => {
      graphVersionsByContextRef.current.delete(currentGraphContext);
      void fetchGraph(true).then(() => checkGraphVersion());
    };
    const handleVisibilityOrFocus = () => {
      if (
        document.visibilityState === "visible" &&
        isGraphVisibleRef.current &&
        navigator.onLine !== false
      ) {
        void checkGraphVersion();
      }
    };
    const interval = window.setInterval(() => {
      if (
        document.visibilityState === "visible" &&
        isGraphVisibleRef.current &&
        navigator.onLine !== false
      ) {
        void checkGraphVersion();
      }
    }, LIVE_POLL_INTERVAL_MS);

    window.addEventListener("orange-memory-graph-updated", handleGraphUpdate);
    window.addEventListener("focus", handleVisibilityOrFocus);
    window.addEventListener("online", handleVisibilityOrFocus);
    document.addEventListener("visibilitychange", handleVisibilityOrFocus);

    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
      graphFetchSequenceRef.current += 1;
      graphFetchControllerRef.current?.abort();
      versionFetchControllerRef.current?.abort();
      detailFetchControllerRef.current?.abort();
      graphFetchControllerRef.current = null;
      versionFetchControllerRef.current = null;
      detailFetchControllerRef.current = null;
      isVersionCheckInFlightRef.current = false;
      window.removeEventListener("orange-memory-graph-updated", handleGraphUpdate);
      window.removeEventListener("focus", handleVisibilityOrFocus);
      window.removeEventListener("online", handleVisibilityOrFocus);
      document.removeEventListener("visibilitychange", handleVisibilityOrFocus);
    };
  }, [checkGraphVersion, currentGraphContext, fetchGraph]);

  useEffect(() => {
    const graph = graphRef.current;

    if (!graph) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        isGraphVisibleRef.current = entry.isIntersecting;

        if (entry.isIntersecting && document.visibilityState === "visible") {
          void checkGraphVersion();
        }

        if (entry.isIntersecting && !hasRevealedGraphRef.current) {
          hasRevealedGraphRef.current = true;
          setIntroVisible(true);
        }
      },
      { threshold: 0.32 },
    );

    observer.observe(graph);

    return () => {
      isGraphVisibleRef.current = false;
      observer.disconnect();
    };
  }, [checkGraphVersion]);

  async function selectNode(node: MemoryNode) {
    setSelectedId(node.id);

    if (node.detailBody || detailLoadingId === node.id) {
      return;
    }

    setDetailLoadingId(node.id);
    detailFetchControllerRef.current?.abort();
    const controller = new AbortController();
    const requestContext = currentGraphContext;
    detailFetchControllerRef.current = controller;

    try {
      const response = await fetch(
        `/api/demo/memory-graph/${encodeURIComponent(node.id)}?${currentGraphQuery}`,
        { cache: "no-store", signal: controller.signal },
      );

      if (!response.ok) {
        throw new Error(`Node detail request failed: ${response.status}`);
      }

      const detail = normalizeNode(await response.json(), node);

      if (detail && activeGraphContextRef.current === requestContext) {
        setMemoryNodeList((current) => {
          const next = current.map((currentNode) => (currentNode.id === node.id ? detail : currentNode));
          memoryNodeListRef.current = next;
          const cachedSnapshot = liveGraphSnapshotsRef.current.get(requestContext);
          if (cachedSnapshot) {
            liveGraphSnapshotsRef.current.set(requestContext, {
              ...cachedSnapshot,
              nodes: next,
            });
          }
          return next;
        });
      }
    } catch (error) {
      if (!isAbortError(error)) {
        console.warn("Unable to load memory node detail", error);
      }
    } finally {
      if (detailFetchControllerRef.current === controller) {
        detailFetchControllerRef.current = null;
        setDetailLoadingId((current) => (current === node.id ? null : current));
      }
    }
  }

  return (
    <div className={`grid gap-5 lg:grid-cols-[minmax(0,1fr)_340px] ${introVisible ? "graph-in-view" : ""}`}>
      <div className="flex flex-col gap-4 rounded-xl border border-[#24352d]/10 bg-white/90 p-4 shadow-[0_14px_40px_rgba(36,53,45,0.07)] backdrop-blur sm:flex-row sm:items-center sm:justify-between lg:col-span-2">
        <div>
          <p className="font-mono text-xs font-bold uppercase tracking-[0.18em] text-[#2f6f5e]">
            Orange memory workspace
          </p>
          <p className="mt-1 text-sm text-[#69756e]">
            Shared notes are visible to everyone using the same workspace name.
          </p>
        </div>
        <div className="grid grid-cols-2 rounded-lg border border-[#d8ded7] bg-[#f2f5f1] p-1">
          {scopeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`h-10 rounded-md px-3 text-xs font-bold transition ${
                scope === option.value
                  ? "bg-[#24352d] text-white shadow-[0_6px_18px_rgba(36,53,45,0.18)]"
                  : "text-[#5f746b] hover:text-[#24352d]"
              }`}
              onClick={() => {
                prepareGraphContext(option.value, userEmail, company);
                setScope(option.value);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={graphRef}
        className="memory-graph-stage relative min-h-[500px] overflow-hidden rounded-2xl border border-[#24352d]/10 shadow-[0_30px_90px_rgba(36,53,45,0.14)] sm:min-h-[620px]"
      >
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.22, maxZoom: 1.12 }}
          minZoom={0.25}
          maxZoom={1.65}
          onNodesChange={onNodesChange}
          onNodeClick={(_event, node) => {
            void selectNode(node.data);
          }}
          onNodeDragStart={() => {
            isDraggingRef.current = true;
          }}
          onNodeDragStop={(_event, _node, nodes) => {
            isDraggingRef.current = false;
            persistFlowPositions(nodes as MemoryFlowNode[]);
          }}
          proOptions={{ hideAttribution: true }}
        >
          <Background variant={BackgroundVariant.Dots} color="#a8b8ae" gap={22} size={1.25} />
          <Controls className="!m-4 !overflow-hidden !rounded-lg !border-[#24352d]/10 !bg-white/95 !shadow-lg" />
          <MiniMap
            className="!right-4 !bottom-4 !hidden !h-28 !w-40 !rounded-lg !border !border-[#24352d]/10 !bg-white/90 !shadow-lg sm:!block"
            maskColor="rgba(232, 238, 232, 0.64)"
            nodeColor={(node) => memoryKindStyles[nodeMemoryKind((node as MemoryFlowNode).data)].accent}
            nodeStrokeWidth={2}
            pannable
            zoomable
          />
        </ReactFlow>

        {hasLoadedGraph && memoryNodeList.length === 0 ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center">
            <div className="max-w-sm rounded-lg border border-dashed border-[#9aa79d] bg-white/92 px-5 py-4 text-sm leading-6 text-[#536057] shadow-sm">
              Nothing has been saved in this scope yet. Finish a useful conversation in the demo below—or write through MCP—to create the first memory.
            </div>
          </div>
        ) : null}

        <div className="absolute left-4 top-4 flex max-w-[calc(100%-2rem)] flex-wrap items-center gap-2 rounded-xl border border-white/80 bg-white/90 p-2 shadow-[0_12px_34px_rgba(36,53,45,0.12)] backdrop-blur-md">
          <div className="pointer-events-none px-2">
            <p className="flex items-center gap-2 text-xs font-bold text-[#24352d]">
              <span className={`h-2 w-2 rounded-full ${graphSyncState === "live" ? "bg-[#28a96b]" : graphSyncState === "stale" ? "bg-[#d7922b]" : "bg-[#c5551c]"}`} />
              {memoryNodeList.length} {memoryNodeList.length === 1 ? "memory" : "memories"}
            </p>
          <p
            aria-live="polite"
              className={`mt-0.5 font-mono text-[0.58rem] font-semibold uppercase tracking-[0.12em] ${
              graphSyncState === "live"
                ? "text-[#2f6f5e]"
                : graphSyncState === "stale"
                  ? "text-[#9a5c16]"
                  : "text-[#9f4218]"
            }`}
          >
            {graphSyncState === "live"
                ? isRefreshing ? "syncing latest notes" : "live · auto-syncing"
              : graphSyncState === "stale"
                  ? "reconnecting · last update shown"
                  : "preview · sign in for live notes"}
          </p>
          </div>
          <span className="h-7 w-px bg-[#24352d]/10" aria-hidden="true" />
          <button type="button" onClick={fitGraph} className="h-8 rounded-md px-2.5 text-xs font-bold text-[#536057] transition hover:bg-[#eef3ed] hover:text-[#24352d]">
            Fit view
          </button>
          <button type="button" onClick={resetGraphLayout} className="h-8 rounded-md px-2.5 text-xs font-bold text-[#536057] transition hover:bg-[#eef3ed] hover:text-[#24352d]">
            Re-layout
          </button>
        </div>
      </div>

      <aside className="rounded-2xl border border-[#24352d]/10 bg-white p-6 shadow-[0_18px_46px_rgba(36,53,45,0.10)] lg:max-h-[620px] lg:overflow-y-auto">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#2f6f5e]">
          Memory details
        </p>
        <h3 className="mt-4 text-2xl font-semibold text-[#161b18]">{selectedNode?.label}</h3>
        <div className="mt-3 flex flex-wrap gap-2">
          <span className="rounded-full bg-[#fff8ec] px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.12em] text-[#c5551c]">
            {selectedNode?.kind}
          </span>
          {selectedNode?.metadata?.memoryKind ? (
            <span className="rounded-full bg-[#eefbf8] px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.12em] text-[#2f7f78]">
              {selectedNode.metadata.memoryKind.replace("_", " ")}
            </span>
          ) : null}
          {selectedNode?.metadata?.status ? (
            <span className="rounded-full bg-[#f1faf5] px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.12em] text-[#2f6f5e]">
              {selectedNode.metadata.status}
            </span>
          ) : null}
          {selectedNode?.score ? (
            <span className="rounded-full bg-[#f7f9f6] px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.12em] text-[#5f746b]">
              {Math.round(selectedNode.score * 100)}%
            </span>
          ) : null}
          {selectedNode?.outcome ? (
            <span className={`rounded-full px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.12em] ${outcomeClass[selectedNode.outcome]}`}>
              {selectedNode.outcome}
            </span>
          ) : null}
          <span
            className={`rounded-full px-2.5 py-1 font-mono text-xs font-semibold uppercase tracking-[0.12em] ${
              selectedScope === "global" ? "bg-[#f5f2ff] text-[#55479a]" : "bg-[#fff8ec] text-[#8f3b14]"
            }`}
          >
            {selectedScope === "global" ? "Shared" : "Private"}
          </span>
        </div>
        <p className="mt-5 text-sm leading-6 text-[#536057]">{selectedNode?.summary}</p>
        {selectedNode?.kind === "Insight" ? (
          <dl className="mt-5 grid gap-3 rounded-md border border-[#2f7f78]/10 bg-[#eefbf8] p-4 text-sm text-[#38514d]">
            {selectedNode.what ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#2f7f78]">What</dt>
                <dd className="mt-1 leading-6">{selectedNode.what}</dd>
              </div>
            ) : null}
            {selectedNode.why ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#2f7f78]">Why</dt>
                <dd className="mt-1 leading-6">{selectedNode.why}</dd>
              </div>
            ) : null}
            {selectedNode.how ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#2f7f78]">Resolution</dt>
                <dd className="mt-1 leading-6">{selectedNode.how}</dd>
              </div>
            ) : null}
            {selectedNode.outcome ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#2f7f78]">Outcome</dt>
                <dd className="mt-1 leading-6">{selectedNode.outcome}</dd>
              </div>
            ) : null}
            {selectedNode.tags?.length ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#2f7f78]">Tags</dt>
                <dd className="mt-2 flex flex-wrap gap-2">
                  {selectedNode.tags.map((tag) => (
                    <span key={tag} className="rounded-full bg-white px-2.5 py-1 font-mono text-xs font-semibold text-[#2f7f78]">
                      {tag}
                    </span>
                  ))}
                </dd>
              </div>
            ) : null}
          </dl>
        ) : null}
        {selectedScope === "global" ? (
          <p className="mt-3 rounded-md border border-[#6f61b5]/15 bg-[#f5f2ff] px-3 py-2 text-sm leading-6 text-[#55479a]">
            Visible to members of this company memory space
          </p>
        ) : null}
        <div className="mt-5 rounded-md bg-[#f7f3e8] p-4 text-sm leading-6 text-[#3f4b44]">
          {detailLoadingId === selectedNode?.id ? (
            <span className="text-[#6b746e]">Loading the stored context...</span>
          ) : (
            <>
              {selectedNode?.detailTitle ? <p className="font-semibold text-[#24352d]">{selectedNode.detailTitle}</p> : null}
              <p className={selectedNode?.detailTitle ? "mt-2" : undefined}>
                {selectedNode?.detailBody ?? "Select this memory again to load its full stored context."}
              </p>
            </>
          )}
        </div>
        {selectedNode?.rawContext ? (
          <details className="mt-3 rounded-md border border-[#24352d]/10 bg-[#fbfaf5] p-3 text-sm leading-6 text-[#3f4b44]">
            <summary className="cursor-pointer font-mono text-xs font-semibold uppercase tracking-[0.14em] text-[#879189]">
              Full context
            </summary>
            <p className="mt-3 whitespace-pre-wrap">{selectedNode.rawContext}</p>
          </details>
        ) : null}
        {selectedNode?.metadata || selectedDate ? (
          <dl className="mt-5 grid gap-3 text-sm text-[#536057]">
            {selectedScope !== "global" && selectedNode.metadata?.owner ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#879189]">Owner</dt>
                <dd className="mt-1 text-[#24352d]">{selectedNode.metadata.owner}</dd>
              </div>
            ) : null}
            {selectedNode.metadata?.repo ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#879189]">Repo</dt>
                <dd className="mt-1 text-[#24352d]">{selectedNode.metadata.repo}</dd>
              </div>
            ) : null}
            {selectedDate ? (
              <div>
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#879189]">Captured</dt>
                <dd className="mt-1 text-[#24352d]">{selectedDate}</dd>
              </div>
            ) : null}
          </dl>
        ) : null}
        {selectedNode?.evidence?.length ? (
          <div className="mt-5">
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#879189]">Evidence</p>
            <ul className="mt-2 space-y-2 text-sm leading-6 text-[#536057]">
              {selectedNode.evidence.slice(0, 3).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {selectedNode?.relatedFiles?.length ? (
          <div className="mt-5">
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#879189]">Files</p>
            <div className="mt-2 flex flex-wrap gap-2">
              {selectedNode.relatedFiles.slice(0, 4).map((file) => (
                <span key={file} className="rounded-md bg-[#f7f9f6] px-2 py-1 font-mono text-xs text-[#344740]">
                  {file}
                </span>
              ))}
            </div>
          </div>
        ) : null}
        {selectedNode?.nextActions?.length ? (
          <div className="mt-5">
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#879189]">Next actions</p>
            <ul className="mt-2 space-y-2 text-sm leading-6 text-[#536057]">
              {selectedNode.nextActions.slice(0, 3).map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </aside>
    </div>
  );
}
