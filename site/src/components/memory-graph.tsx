"use client";

import dagre from "dagre";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useNodesState,
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

const NODE_WIDTH = 188;
const NODE_HEIGHT = 118;
const STORAGE_PREFIX = "orange-memory-graph-positions:v2";

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

const scopeOptions: ReadonlyArray<{ value: MemoryScopeFilter; label: string }> = [
  { value: "user", label: "My Memory" },
  { value: "global", label: "Global" },
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
  return value === "global" || value === "shared" ? "global" : "user";
}

function normalizeOutcome(value: unknown): InsightOutcomeValue | undefined {
  return value === "resolved" || value === "exploratory" || value === "partial" || value === "abandoned"
    ? value
    : undefined;
}

function normalizeMemoryKind(value: unknown): MemoryKind {
  return value === "technical_insight" ||
    value === "user_fact" ||
    value === "company_fact" ||
    value === "preference" ||
    value === "steering"
    ? value
    : "unknown";
}

function normalizeKind(value: unknown): MemoryNode["kind"] {
  const kind = asString(value);

  if (
    kind === "Insight" ||
    kind === "Problem" ||
    kind === "Attempt" ||
    kind === "Solution" ||
    kind === "Artifact" ||
    kind === "Concept" ||
    kind === "Session"
  ) {
    return kind;
  }

  return "Concept";
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
        owner: asString(value.metadata.owner),
        repo: asString(value.metadata.repo),
        createdAt: asString(value.metadata.createdAt),
        status: asString(value.metadata.status),
        scope: normalizeScope(value.metadata.scope),
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
    label: asString(value.label) ?? existing?.label ?? "Untitled memory",
    kind: normalizeKind(value.kind ?? value.type ?? existing?.kind),
    x,
    y,
    summary: asString(value.summary) ?? existing?.summary ?? "New memory node waiting for context.",
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
    label: asString(value.label),
    strength: asNumber(value.strength),
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
  graph.setGraph({ rankdir: "LR", nodesep: 70, ranksep: 110, marginx: 40, marginy: 40 });

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

    const radius = Math.max(96, movable.length * 24);
    movable.forEach((id, index) => {
      const angle = (index / movable.length) * Math.PI * 2;
      positions.set(id, {
        x: centroid.x + Math.cos(angle) * radius,
        y: centroid.y + Math.sin(angle) * radius * 0.72,
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
      type: "smoothstep",
      data: { strength: edge.strength, related },
      markerEnd: related ? undefined : { type: MarkerType.ArrowClosed, color: "#9aa79d" },
      labelBgBorderRadius: 5,
      labelBgPadding: [6, 3],
      labelBgStyle: { fill: related ? "#fbfaf5" : "#ffffff", fillOpacity: 0.86 },
      style: {
        stroke: related ? "#b8aaa0" : "#9aa79d",
        strokeDasharray: related ? "6 7" : undefined,
        strokeOpacity: related ? 0.62 : 0.38 + (edge.strength ?? 0.7) * 0.22,
        strokeWidth: related ? 1.5 : 1.2 + (edge.strength ?? 0.7),
      },
    };
  });
}

function MemoryCardNode({ data, selected }: NodeProps<MemoryFlowNode>) {
  const memoryKind = nodeMemoryKind(data);
  const style = memoryKindStyles[memoryKind];
  const scope = nodeScope(data);

  return (
    <button
      type="button"
      className={`group w-[11.75rem] rounded-lg border px-3 py-3 text-left shadow-[0_16px_38px_rgba(36,53,45,0.12)] transition ${
        selected ? "ring-2 ring-[#c5551c] ring-offset-2 ring-offset-[#fbfaf5]" : "hover:-translate-y-0.5"
      } ${data.isNew ? "animate-[node-pop_520ms_ease_forwards]" : ""}`}
      style={{ background: style.bg, borderColor: style.border, color: style.text }}
    >
      <Handle type="target" position={Position.Left} className="!h-2 !w-2 !border-0" style={{ background: style.accent }} />
      <span className="flex items-center justify-between gap-2">
        <span className="font-mono text-[0.66rem] font-semibold uppercase tracking-[0.14em]">
          {memoryKind.replace("_", " ")}
        </span>
        <span
          className="h-2 w-2 rounded-full"
          style={{ background: scope === "global" ? "#55479a" : "#c5551c" }}
          aria-hidden="true"
        />
      </span>
      <span className="mt-1 block text-sm font-semibold leading-5 text-[#182019]">{truncateLabel(data.label)}</span>
      <span className="mt-2 line-clamp-2 block text-xs leading-5 opacity-80">{data.summary}</span>
      <Handle type="source" position={Position.Right} className="!h-2 !w-2 !border-0" style={{ background: style.accent }} />
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
  const [memoryNodeList, setMemoryNodeList] = useState(visibleMemoryNodes);
  const [memoryEdgeList, setMemoryEdgeList] = useState<MemoryEdge[]>(visibleFallbackEdges);
  const [selectedId, setSelectedId] = useState("cors-insight");
  const [scope, setScope] = useState<MemoryScopeFilter>("user");
  const [nodePositions, setNodePositions] = useState<Record<string, StoredPosition>>(() => readStoredPositions("user"));
  const [flowNodes, setFlowNodes, onNodesChange] = useNodesState<MemoryFlowNode>(
    layoutNodes(visibleMemoryNodes, visibleFallbackEdges, readStoredPositions("user"), new Set()),
  );
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [graphSource, setGraphSource] = useState<"backend" | "fallback">("fallback");
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
  const graphRef = useRef<HTMLDivElement>(null);
  const memoryNodeListRef = useRef(visibleMemoryNodes);
  const memoryEdgeListRef = useRef<MemoryEdge[]>(visibleFallbackEdges);
  const seenNodeIdsRef = useRef(new Set(visibleMemoryNodes.map((node) => node.id)));
  const isGraphVisibleRef = useRef(false);
  const hasRevealedGraphRef = useRef(false);
  const isDraggingRef = useRef(false);
  const graphSourceRef = useRef<"backend" | "fallback">("fallback");
  const nextFallbackPollAtRef = useRef(0);
  const lastHydratedSignatureRef = useRef(
    graphHydrationSignature(visibleMemoryNodes, visibleFallbackEdges, "user"),
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

  const hydrateFlowNodes = useCallback(
    (
      nextNodes: MemoryNode[],
      nextEdges: MemoryEdge[],
      nextScope: MemoryScopeFilter,
      freshIds: Set<string> = new Set(),
    ) => {
      if (isDraggingRef.current) {
        return;
      }
      const signature = graphHydrationSignature(nextNodes, nextEdges, nextScope);
      if (freshIds.size === 0 && lastHydratedSignatureRef.current === signature) {
        return;
      }

      const storedPositions = readStoredPositions(nextScope);
      lastHydratedSignatureRef.current = signature;
      setNodePositions(storedPositions);
      setFlowNodes(layoutNodes(nextNodes, nextEdges, storedPositions, freshIds));
    },
    [setFlowNodes],
  );

  useEffect(() => {
    memoryNodeListRef.current = memoryNodeList;
  }, [memoryNodeList]);

  useEffect(() => {
    memoryEdgeListRef.current = memoryEdgeList;
  }, [memoryEdgeList]);

  useEffect(() => {
    function handleProfileUpdate() {
      try {
        const storedProfile = window.localStorage.getItem("orange-demo-profile");
        if (storedProfile) {
          const parsed = JSON.parse(storedProfile) as { email?: unknown; company?: unknown };
          if (typeof parsed.email === "string") {
            setUserEmail(parsed.email.trim().toLowerCase());
          }
          if (typeof parsed.company === "string") {
            setCompany(parsed.company.trim());
          }
        }
      } catch {
        setUserEmail("");
        setCompany("");
      }
    }

    window.addEventListener("orange-demo-profile-updated", handleProfileUpdate);
    return () => window.removeEventListener("orange-demo-profile-updated", handleProfileUpdate);
  }, []);

  const fetchGraph = useCallback(async (showRefreshing = true, refresh = false) => {
    if (showRefreshing) {
      setIsRefreshing(true);
    }

    try {
      const params = new URLSearchParams({ scope });
      if (userEmail) {
        params.set("user_email", userEmail);
      }
      if (company) {
        params.set("company", company);
      }
      if (refresh) {
        params.set("refresh", String(Date.now()));
      }
      const response = await fetch(`/api/demo/memory-graph?${params.toString()}`);

      if (!response.ok) {
        throw new Error(`Graph request failed: ${response.status}`);
      }

      const graph: unknown = await response.json();

      if (!isRecord(graph)) {
        return;
      }
      const nextGraphSource = graph.source === "backend" ? "backend" : "fallback";
      graphSourceRef.current = nextGraphSource;
      nextFallbackPollAtRef.current = nextGraphSource === "fallback" ? Date.now() + 45_000 : 0;
      setGraphSource(nextGraphSource);
      setHasLoadedGraph(true);

      const currentMemoryNodes = memoryNodeListRef.current;
      const currentMemoryEdges = memoryEdgeListRef.current;
      let freshIdSet = new Set<string>();
      const existingById = new Map(currentMemoryNodes.map((node) => [node.id, node]));
      const apiNodes = Array.isArray(graph.nodes)
        ? graph.nodes
            .map((node) => normalizeNode(node, isRecord(node) ? existingById.get(asString(node.id) ?? "") : undefined))
            .filter((node): node is MemoryNode => Boolean(node))
        : [];
      const nextMemoryNodes =
        apiNodes.length > 0 || graph.source === "backend"
          ? apiNodes
          : visibleMemoryNodes.filter((node) => nodeScope(node) === scope);

      const freshIds = nextMemoryNodes
        .map((node) => node.id)
        .filter((id) => !seenNodeIdsRef.current.has(id));
      freshIds.forEach((id) => seenNodeIdsRef.current.add(id));
      if (freshIds.length > 0) {
        freshIdSet = new Set(freshIds);
        window.setTimeout(() => {
          setFlowNodes((current) =>
            current.map((node) => ({
              ...node,
              data: { ...node.data, isNew: false },
            })),
          );
        }, 600);
      }

      if (!nextMemoryNodes.some((node) => node.id === selectedId)) {
        setSelectedId(nextMemoryNodes[0]?.id ?? "");
      }

      let nextMemoryEdges = currentMemoryEdges;
      if (Array.isArray(graph.edges)) {
        const nextEdges = graph.edges.map(normalizeEdge).filter((edge): edge is MemoryEdge => Boolean(edge));
        nextMemoryEdges =
          nextEdges.length > 0 || graph.source === "backend"
            ? nextEdges
            : visibleFallbackEdges.filter((edge) => {
                const scopedNodeIds = new Set(
                  visibleMemoryNodes.filter((node) => nodeScope(node) === scope).map((node) => node.id),
                );
                return scopedNodeIds.has(edge.source) && scopedNodeIds.has(edge.target);
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
      hydrateFlowNodes(nextMemoryNodes, nextMemoryEdges, scope, freshIdSet);
    } catch (error) {
      console.warn("Unable to refresh memory graph", error);
    } finally {
      if (showRefreshing) {
        setIsRefreshing(false);
      }
    }
  }, [company, hydrateFlowNodes, scope, selectedId, setFlowNodes, userEmail]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => {
      void fetchGraph(false);
    }, 0);

    const handleGraphUpdate = () => {
      void fetchGraph(true, true);
    };
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible" && isGraphVisibleRef.current) {
        if (graphSourceRef.current === "fallback" && Date.now() < nextFallbackPollAtRef.current) {
          return;
        }
        void fetchGraph();
      }
    }, 6000);

    window.addEventListener("orange-memory-graph-updated", handleGraphUpdate);

    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
      window.removeEventListener("orange-memory-graph-updated", handleGraphUpdate);
    };
  }, [fetchGraph]);

  useEffect(() => {
    const graph = graphRef.current;

    if (!graph) {
      return;
    }

    const observer = new IntersectionObserver(
      ([entry]) => {
        isGraphVisibleRef.current = entry.isIntersecting;

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
  }, []);

  async function selectNode(node: MemoryNode) {
    setSelectedId(node.id);

    if (node.detailBody || detailLoadingId === node.id) {
      return;
    }

    setDetailLoadingId(node.id);

    try {
      const params = new URLSearchParams({ scope });
      if (userEmail) {
        params.set("user_email", userEmail);
      }
      if (company) {
        params.set("company", company);
      }
      const response = await fetch(`/api/demo/memory-graph/${encodeURIComponent(node.id)}?${params.toString()}`);

      if (!response.ok) {
        throw new Error(`Node detail request failed: ${response.status}`);
      }

      const detail = normalizeNode(await response.json(), node);

      if (detail) {
        setMemoryNodeList((current) => current.map((currentNode) => (currentNode.id === node.id ? detail : currentNode)));
      }
    } catch (error) {
      console.warn("Unable to load memory node detail", error);
    } finally {
      setDetailLoadingId((current) => (current === node.id ? null : current));
    }
  }

  return (
    <div className={`grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px] ${introVisible ? "graph-in-view" : ""}`}>
      <div className="flex flex-col gap-3 rounded-lg border border-[#24352d]/10 bg-white p-3 shadow-sm sm:flex-row sm:items-center sm:justify-between lg:col-span-2">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#5f746b]">
          Memory scope
        </p>
        <div className="grid grid-cols-2 rounded-md border border-[#d8ded7] bg-[#f7f9f6] p-1">
          {scopeOptions.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`h-9 rounded px-3 text-xs font-bold transition ${
                scope === option.value
                  ? "bg-white text-[#24352d] shadow-sm"
                  : "text-[#5f746b] hover:text-[#24352d]"
              }`}
              onClick={() => {
                setScope(option.value);
                const scopedNodes = visibleMemoryNodes.filter((node) => nodeScope(node) === option.value);
                const scopedNodeIds = new Set(scopedNodes.map((node) => node.id));
                const scopedEdges = visibleFallbackEdges.filter(
                  (edge) => scopedNodeIds.has(edge.source) && scopedNodeIds.has(edge.target),
                );
                memoryNodeListRef.current = scopedNodes;
                memoryEdgeListRef.current = scopedEdges;
                setMemoryNodeList(scopedNodes);
                setMemoryEdgeList(scopedEdges);
                hydrateFlowNodes(scopedNodes, scopedEdges, option.value);
              }}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>

      <div
        ref={graphRef}
        className="relative min-h-[420px] overflow-hidden rounded-lg border border-[#24352d]/10 bg-[#fbfaf5] shadow-[0_24px_70px_rgba(36,53,45,0.12)] sm:min-h-[500px]"
      >
        <ReactFlow
          nodes={flowNodes}
          edges={flowEdges}
          nodeTypes={nodeTypes}
          fitView
          minZoom={0.25}
          maxZoom={1.8}
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
          <Background color="#d8ded7" gap={24} />
          <Controls className="!border-[#24352d]/10 !bg-white/90 !shadow-sm" />
          <MiniMap
            className="!right-4 !bottom-4 !h-28 !w-40 !rounded-md !border !border-[#24352d]/10 !bg-white/90 !shadow-sm"
            maskColor="rgba(36, 53, 45, 0.08)"
            nodeColor={(node) => memoryKindStyles[nodeMemoryKind((node as MemoryFlowNode).data)].accent}
            nodeStrokeWidth={2}
            pannable
            zoomable
          />
        </ReactFlow>

        {hasLoadedGraph && memoryNodeList.length === 0 ? (
          <div className="pointer-events-none absolute inset-0 flex items-center justify-center px-6 text-center">
            <div className="max-w-sm rounded-lg border border-dashed border-[#9aa79d] bg-white/92 px-5 py-4 text-sm leading-6 text-[#536057] shadow-sm">
              No notes are visible in this scope yet. Complete a conversation with matching profile details to create private or shared memory here.
            </div>
          </div>
        ) : null}

        <div className="pointer-events-none absolute left-5 top-5 rounded-md border border-[#24352d]/10 bg-white/88 px-3 py-2 shadow-sm backdrop-blur">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#c5551c]">
            Live neighborhood
          </p>
          <p className="mt-1 text-xs text-[#536057]">
            {memoryNodeList.length} nodes {isRefreshing ? "syncing" : "linked"}
          </p>
          <p
            className={`mt-1 font-mono text-[0.65rem] font-semibold uppercase tracking-[0.14em] ${
              graphSource === "backend" ? "text-[#2f6f5e]" : "text-[#9f4218]"
            }`}
          >
            {graphSource === "backend" ? "backend sync" : "demo fallback"}
          </p>
        </div>
      </div>

      <aside className="rounded-lg border border-[#24352d]/10 bg-white p-5 shadow-[0_18px_46px_rgba(36,53,45,0.10)]">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#2f6f5e]">
          Selected node
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
                <dt className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#2f7f78]">How</dt>
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
            Contributed anonymously from shared sessions
          </p>
        ) : null}
        <div className="mt-5 rounded-md bg-[#f7f3e8] p-4 text-sm leading-6 text-[#3f4b44]">
          {detailLoadingId === selectedNode?.id ? (
            <span className="text-[#6b746e]">Loading node context...</span>
          ) : (
            <>
              {selectedNode?.detailTitle ? <p className="font-semibold text-[#24352d]">{selectedNode.detailTitle}</p> : null}
              <p className={selectedNode?.detailTitle ? "mt-2" : undefined}>
                {selectedNode?.detailBody ?? "Click the node again to load its stored context."}
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
            <p className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em] text-[#879189]">Next</p>
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
