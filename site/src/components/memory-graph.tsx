"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

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

type MemoryScopeValue = "user" | "global";
type MemoryScopeFilter = MemoryScopeValue | "both";
type InsightOutcomeValue = "resolved" | "exploratory" | "partial" | "abandoned";

type MemoryEdge = {
  id: string;
  source: string;
  target: string;
  label?: string;
  strength?: number;
};

type NodePosition = Pick<MemoryNode, "x" | "y">;
type GraphViewport = { scale: number; x: number; y: number };

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
    },
  },
];

const fallbackEdges: MemoryEdge[] = [
  { id: "cors-steering", source: "cors-insight", target: "website-steering", label: "private", strength: 0.68 },
  { id: "spain-markdown", source: "spain-gtm", target: "markdown-memory", label: "company", strength: 0.72 },
  { id: "spain-aws", source: "spain-gtm", target: "aws-glue-fact", label: "shared", strength: 0.58 },
  { id: "markdown-aws", source: "markdown-memory", target: "aws-glue-fact", label: "facts", strength: 0.64 },
];

const visibleMemoryNodes = memoryNodes.filter((node) => node.kind !== "Session");
const visibleMemoryNodeIds = new Set(visibleMemoryNodes.map((node) => node.id));
const visibleFallbackEdges = fallbackEdges.filter(
  (edge) => visibleMemoryNodeIds.has(edge.source) && visibleMemoryNodeIds.has(edge.target),
);

const kindClass: Record<MemoryNode["kind"], string> = {
  Insight: "border-[#2f7f78] bg-[#eefbf8] text-[#1f5d58]",
  Problem: "border-[#c5551c] bg-[#fff8ec] text-[#8f3b14]",
  Attempt: "border-[#c3a46b] bg-[#fffdf6] text-[#6d5421]",
  Solution: "border-[#2f6f5e] bg-[#f1faf5] text-[#205545]",
  Artifact: "border-[#5f746b] bg-[#f7f9f6] text-[#344740]",
  Concept: "border-[#839a8d] bg-white text-[#40554b]",
  Session: "border-[#24352d] bg-[#f6f7f4] text-[#24352d]",
};

const outcomeClass: Record<InsightOutcomeValue, string> = {
  resolved: "bg-[#f1faf5] text-[#2f6f5e]",
  exploratory: "bg-[#eef6ff] text-[#2f5f8f]",
  partial: "bg-[#fff8ec] text-[#9a5c16]",
  abandoned: "bg-[#f3f4f2] text-[#5f6a64]",
};

const scopeOptions: ReadonlyArray<{ value: MemoryScopeFilter; label: string }> = [
  { value: "user", label: "My Memory" },
  { value: "global", label: "Global" },
];

const scopeNodeClass: Record<MemoryScopeValue, string> = {
  user: "shadow-[0_16px_38px_rgba(197,85,28,0.16)]",
  global: "shadow-[0_16px_38px_rgba(85,71,154,0.16)]",
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

function truncateLabel(value: string, maxLength = 30) {
  return value.length <= maxLength ? value : `${value.slice(0, maxLength - 1).trim()}...`;
}

function clampPosition(value: number, min: number, max: number) {
  return Math.min(max, Math.max(min, value));
}

function hashNodeId(id: string) {
  let hash = 0;

  for (let index = 0; index < id.length; index += 1) {
    hash = (hash * 31 + id.charCodeAt(index)) >>> 0;
  }

  return hash;
}

function positionForNode(id: string) {
  const hash = hashNodeId(id);
  const angle = ((hash % 360) / 180) * Math.PI;
  const radius = 0.72 + ((hash >> 8) % 24) / 100;

  return {
    x: clampPosition(50 + Math.cos(angle) * 34 * radius, 12, 88),
    y: clampPosition(50 + Math.sin(angle) * 28 * radius, 14, 84),
  };
}

function normalizeKind(value: unknown): MemoryNode["kind"] {
  const kind = asString(value);

  if (kind && kind in kindClass) {
    return kind as MemoryNode["kind"];
  }

  return "Concept";
}

function nodeScope(node?: MemoryNode): MemoryScopeValue {
  return node?.metadata?.scope ?? "user";
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
  const coordinates = {
    x: asNumber(value.x),
    y: asNumber(value.y),
  };
  const position =
    coordinates.x !== undefined && coordinates.y !== undefined
      ? {
          x: clampPosition(coordinates.x, 12, 88),
          y: clampPosition(coordinates.y, 14, 84),
        }
      : existing
        ? { x: existing.x, y: existing.y }
        : positionForNode(id);
  const metadata = isRecord(value.metadata)
    ? {
        owner: asString(value.metadata.owner),
        repo: asString(value.metadata.repo),
        createdAt: asString(value.metadata.createdAt),
        status: asString(value.metadata.status),
        scope: normalizeScope(value.metadata.scope),
        outcome: normalizeOutcome(value.metadata.outcome),
        tags: asStringArray(value.metadata.tags),
      }
    : existing?.metadata;
  const detailBody = asString(value.detail) ?? asString(detail?.body) ?? existing?.detailBody;
  const rawContext = asString(detail?.fullContext) ?? asString(detail?.rawDescription) ?? existing?.rawContext;
  const tags = asStringArray(detail?.tags) ?? metadata?.tags ?? existing?.tags;
  const outcome = normalizeOutcome(detail?.outcome) ?? metadata?.outcome ?? existing?.outcome;

  return {
    id,
    label: asString(value.label) ?? existing?.label ?? "Untitled memory",
    kind: normalizeKind(value.kind ?? value.type ?? existing?.kind),
    x: position.x,
    y: position.y,
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

export default function MemoryGraph() {
  const [nodes, setNodes] = useState(visibleMemoryNodes);
  const [edges, setEdges] = useState<MemoryEdge[]>(visibleFallbackEdges);
  const [selectedId, setSelectedId] = useState("cors-insight");
  const [scope, setScope] = useState<MemoryScopeFilter>("user");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [graphSource, setGraphSource] = useState<"backend" | "fallback">("fallback");
  const [hasLoadedGraph, setHasLoadedGraph] = useState(false);
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);
  const [newNodeIds, setNewNodeIds] = useState<Set<string>>(new Set());
  const [viewport, setViewport] = useState({ scale: 1, x: 0, y: 0 });
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
  const graphLayerRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const panRef = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);
  const viewportRef = useRef<GraphViewport>(viewport);
  const nodePositionsRef = useRef<Record<string, NodePosition>>(
    Object.fromEntries(visibleMemoryNodes.map((node) => [node.id, { x: node.x, y: node.y }])),
  );
  const nodeRefs = useRef<Record<string, HTMLButtonElement | null>>({});
  const edgeRefs = useRef<Record<string, SVGLineElement | null>>({});
  const edgeLabelRefs = useRef<Record<string, SVGTextElement | null>>({});
  const pointerCleanupRef = useRef<(() => void) | null>(null);
  const seenNodeIdsRef = useRef(new Set(visibleMemoryNodes.map((node) => node.id)));

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedId) ?? nodes[0],
    [nodes, selectedId],
  );
  const selectedDate = formatDate(selectedNode?.metadata?.createdAt);
  const selectedScope = nodeScope(selectedNode);

  const applyViewport = useCallback((nextViewport: GraphViewport) => {
    const layer = graphLayerRef.current;
    if (!layer) {
      return;
    }

    layer.style.transform = `translate(${nextViewport.x}px, ${nextViewport.y}px) scale(${nextViewport.scale})`;
  }, []);

  const updateEdgePosition = useCallback((edge: MemoryEdge) => {
    const start = nodePositionsRef.current[edge.source];
    const end = nodePositionsRef.current[edge.target];
    const line = edgeRefs.current[edge.id];

    if (!start || !end || !line) {
      return;
    }

    line.setAttribute("x1", `${start.x}%`);
    line.setAttribute("y1", `${start.y}%`);
    line.setAttribute("x2", `${end.x}%`);
    line.setAttribute("y2", `${end.y}%`);

    const label = edgeLabelRefs.current[edge.id];
    if (label) {
      label.setAttribute("x", `${(start.x + end.x) / 2}%`);
      label.setAttribute("y", `${(start.y + end.y) / 2}%`);
    }
  }, []);

  const updateConnectedEdges = useCallback(
    (nodeId?: string) => {
      for (const edge of edges) {
        if (nodeId && edge.source !== nodeId && edge.target !== nodeId) {
          continue;
        }
        updateEdgePosition(edge);
      }
    },
    [edges, updateEdgePosition],
  );

  const applyNodePosition = useCallback((id: string, position: NodePosition) => {
    const node = nodeRefs.current[id];
    if (!node) {
      return;
    }

    node.style.left = `${position.x}%`;
    node.style.top = `${position.y}%`;
  }, []);

  useEffect(() => {
    viewportRef.current = viewport;
    applyViewport(viewport);
  }, [applyViewport, viewport]);

  useEffect(() => {
    const nextPositions = Object.fromEntries(nodes.map((node) => [node.id, { x: node.x, y: node.y }]));
    nodePositionsRef.current = nextPositions;

    for (const node of nodes) {
      applyNodePosition(node.id, nextPositions[node.id]);
    }
    updateConnectedEdges();
  }, [applyNodePosition, nodes, updateConnectedEdges]);

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

  const resolveOverlaps = useCallback((input: MemoryNode[]) => {
    const next = input.map((node) => ({ ...node }));

    for (let i = 0; i < next.length; i += 1) {
      for (let j = i + 1; j < next.length; j += 1) {
        const dx = next[j].x - next[i].x;
        const dy = next[j].y - next[i].y;

        if (Math.abs(dx) < 10 && Math.abs(dy) < 8) {
          const direction = j % 2 === 0 ? 1 : -1;
          next[j].x = clampPosition(next[j].x + 8 * direction, 12, 88);
          next[j].y = clampPosition(next[j].y + 6, 14, 84);
        }
      }
    }

    return next;
  }, []);

  const fetchGraph = useCallback(async (showRefreshing = true) => {
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
      const response = await fetch(`/api/demo/memory-graph?${params.toString()}`, {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Graph request failed: ${response.status}`);
      }

      const graph: unknown = await response.json();

      if (!isRecord(graph)) {
        return;
      }
      setGraphSource(graph.source === "backend" ? "backend" : "fallback");
      setHasLoadedGraph(true);

      setNodes((current) => {
        const existingById = new Map(current.map((node) => [node.id, node]));
        const nextNodes = Array.isArray(graph.nodes)
          ? graph.nodes
              .map((node) => normalizeNode(node, isRecord(node) ? existingById.get(asString(node.id) ?? "") : undefined))
              .filter((node): node is MemoryNode => Boolean(node))
          : [];

        const freshIds = nextNodes
          .map((node) => node.id)
          .filter((id) => !seenNodeIdsRef.current.has(id));
        freshIds.forEach((id) => seenNodeIdsRef.current.add(id));
        if (freshIds.length > 0) {
          setNewNodeIds(new Set(freshIds));
          window.setTimeout(() => setNewNodeIds(new Set()), 500);
        }

        const resolvedNodes = resolveOverlaps(nextNodes);
        if (!resolvedNodes.some((node) => node.id === selectedId)) {
          setSelectedId(resolvedNodes[0]?.id ?? "");
        }
        return resolvedNodes;
      });

      if (Array.isArray(graph.edges)) {
        const nextEdges = graph.edges.map(normalizeEdge).filter((edge): edge is MemoryEdge => Boolean(edge));
        setEdges(nextEdges);
      }
    } catch (error) {
      console.warn("Unable to refresh memory graph", error);
    } finally {
      if (showRefreshing) {
        setIsRefreshing(false);
      }
    }
  }, [company, resolveOverlaps, scope, selectedId, userEmail]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => {
      void fetchGraph(false);
    }, 0);

    const handleGraphUpdate = () => {
      void fetchGraph();
    };
    const interval = window.setInterval(() => {
      if (document.visibilityState === "visible") {
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
        if (entry.isIntersecting) {
          setIntroVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.32 },
    );

    observer.observe(graph);

    return () => observer.disconnect();
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
      const response = await fetch(`/api/demo/memory-graph/${encodeURIComponent(node.id)}?${params.toString()}`, {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Node detail request failed: ${response.status}`);
      }

      const detail = normalizeNode(await response.json(), node);

      if (detail) {
        setNodes((current) => current.map((currentNode) => (currentNode.id === node.id ? detail : currentNode)));
      }
    } catch (error) {
      console.warn("Unable to load memory node detail", error);
    } finally {
      setDetailLoadingId((current) => (current === node.id ? null : current));
    }
  }

  function moveNode(clientX: number, clientY: number) {
    const drag = dragRef.current;
    const bounds = graphLayerRef.current?.getBoundingClientRect();

    if (!drag || !bounds) {
      return;
    }

    const nextPosition = {
      x: clampPosition(((clientX - drag.dx - bounds.left) / bounds.width) * 100, 12, 88),
      y: clampPosition(((clientY - drag.dy - bounds.top) / bounds.height) * 100, 14, 84),
    };

    nodePositionsRef.current[drag.id] = nextPosition;
    applyNodePosition(drag.id, nextPosition);
    updateConnectedEdges(drag.id);
  }

  function movePan(clientX: number, clientY: number) {
    const pan = panRef.current;
    if (!pan) {
      return;
    }
    const nextViewport = {
      ...viewportRef.current,
      x: pan.x + clientX - pan.startX,
      y: pan.y + clientY - pan.startY,
    };
    viewportRef.current = nextViewport;
    applyViewport(nextViewport);
  }

  function commitPointerInteraction() {
    const drag = dragRef.current;
    const pan = panRef.current;

    if (drag) {
      setNodes((current) =>
        current.map((node) => {
          const position = nodePositionsRef.current[node.id];
          return position ? { ...node, ...position } : node;
        }),
      );
    }

    if (pan) {
      setViewport(viewportRef.current);
    }

    dragRef.current = null;
    panRef.current = null;
  }

  function stopWindowPointerTracking() {
    pointerCleanupRef.current?.();
    pointerCleanupRef.current = null;
  }

  function startWindowPointerTracking() {
    stopWindowPointerTracking();

    const handleMove = (event: PointerEvent) => {
      moveNode(event.clientX, event.clientY);
      movePan(event.clientX, event.clientY);
    };
    const handleEnd = () => {
      stopWindowPointerTracking();
      commitPointerInteraction();
    };

    window.addEventListener("pointermove", handleMove, { passive: true });
    window.addEventListener("pointerup", handleEnd, { passive: true });
    window.addEventListener("pointercancel", handleEnd, { passive: true });
    pointerCleanupRef.current = () => {
      window.removeEventListener("pointermove", handleMove);
      window.removeEventListener("pointerup", handleEnd);
      window.removeEventListener("pointercancel", handleEnd);
    };
  }

  useEffect(() => () => stopWindowPointerTracking(), []);

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
              onClick={() => setScope(option.value)}
            >
              {option.label}
            </button>
          ))}
        </div>
      </div>
      <div
        ref={graphRef}
        className="relative min-h-[420px] overflow-hidden rounded-lg border border-[#24352d]/10 bg-[#fbfaf5] shadow-[0_24px_70px_rgba(36,53,45,0.12)] touch-none sm:min-h-[500px]"
        onWheel={(event) => {
          event.preventDefault();
          setViewport((current) => ({
            ...current,
            scale: Math.min(1.8, Math.max(0.72, current.scale + (event.deltaY > 0 ? -0.08 : 0.08))),
          }));
        }}
        onPointerDown={(event) => {
          if (event.target !== event.currentTarget) {
            return;
          }
          panRef.current = {
            x: viewportRef.current.x,
            y: viewportRef.current.y,
            startX: event.clientX,
            startY: event.clientY,
          };
          startWindowPointerTracking();
        }}
        onPointerUp={() => {
          stopWindowPointerTracking();
          commitPointerInteraction();
        }}
        onPointerLeave={() => {
          if (!dragRef.current && !panRef.current) {
            stopWindowPointerTracking();
          }
        }}
      >
        <div
          ref={graphLayerRef}
          className="absolute inset-0"
          style={{
            transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})`,
            transformOrigin: "50% 50%",
          }}
        >
          <svg className="absolute inset-0 h-full w-full" role="presentation">
            {edges.map((edge, index) => {
              const start = nodes.find((node) => node.id === edge.source);
              const end = nodes.find((node) => node.id === edge.target);

              if (!start || !end) {
                return null;
              }

              return (
                <g className="group" key={edge.id}>
                  <line
                    ref={(element) => {
                      edgeRefs.current[edge.id] = element;
                    }}
                    className="graph-edge"
                    x1={`${start.x}%`}
                    y1={`${start.y}%`}
                    x2={`${end.x}%`}
                    y2={`${end.y}%`}
                    stroke="#9aa79d"
                    strokeOpacity={String(0.32 + (edge.strength ?? 0.7) * 0.28)}
                    strokeWidth={String(1 + (edge.strength ?? 0.7))}
                    style={{ animationDelay: `${index * 160}ms` }}
                  />
                  {edge.label ? (
                    <text
                      ref={(element) => {
                        edgeLabelRefs.current[edge.id] = element;
                      }}
                      x={`${(start.x + end.x) / 2}%`}
                      y={`${(start.y + end.y) / 2}%`}
                      className="opacity-0 transition-opacity group-hover:opacity-100"
                      fill="#8f3b14"
                      fontSize="10"
                      fontWeight="700"
                      pointerEvents="none"
                      textAnchor="middle"
                    >
                      {edge.label}
                    </text>
                  ) : null}
                </g>
              );
            })}
          </svg>

          {hasLoadedGraph && nodes.length === 0 ? (
            <div className="absolute inset-0 flex items-center justify-center px-6 text-center">
              <div className="max-w-sm rounded-lg border border-dashed border-[#9aa79d] bg-white/92 px-5 py-4 text-sm leading-6 text-[#536057] shadow-sm">
                No notes are visible in this scope yet. Complete a conversation with matching profile details to create private or shared memory here.
              </div>
            </div>
          ) : null}

          <div className="absolute left-5 top-5 rounded-md border border-[#24352d]/10 bg-white/88 px-3 py-2 shadow-sm backdrop-blur">
            <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#c5551c]">
              Live neighborhood
            </p>
            <p className="mt-1 text-xs text-[#536057]">
              {nodes.length} nodes {isRefreshing ? "syncing" : "linked"}
            </p>
            <p
              className={`mt-1 font-mono text-[0.65rem] font-semibold uppercase tracking-[0.14em] ${
                graphSource === "backend" ? "text-[#2f6f5e]" : "text-[#9f4218]"
              }`}
            >
              {graphSource === "backend" ? "backend sync" : "demo fallback"}
            </p>
          </div>

          {nodes.map((node, index) => {
            const isSelected = node.id === selectedNode?.id;
            const isNew = newNodeIds.has(node.id);
            const currentScope = nodeScope(node);

            return (
              <button
                key={node.id}
                id={`node-${node.id}`}
                ref={(element) => {
                  nodeRefs.current[node.id] = element;
                }}
                type="button"
                className={`memory-node absolute w-[9.75rem] -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-lg border px-3 py-3 text-left transition-[opacity,transform,box-shadow] duration-500 active:cursor-grabbing ${kindClass[node.kind]} ${scopeNodeClass[currentScope]} ${
                  isSelected ? "ring-2 ring-[#c5551c] ring-offset-2 ring-offset-[#fbfaf5]" : "hover:-translate-y-[calc(50%+2px)]"
                } ${isNew ? "scale-0 opacity-0" : "scale-100 opacity-100"}`}
                style={{ left: `${node.x}%`, top: `${node.y}%`, animationDelay: `${index * 200}ms` }}
                onClick={() => {
                  void selectNode(node);
                }}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  const nodeBounds = event.currentTarget.getBoundingClientRect();
                  event.currentTarget.setPointerCapture(event.pointerId);
                  setSelectedId(node.id);
                  nodePositionsRef.current[node.id] = { x: node.x, y: node.y };
                  dragRef.current = {
                    id: node.id,
                    dx: event.clientX - (nodeBounds.left + nodeBounds.width / 2),
                    dy: event.clientY - (nodeBounds.top + nodeBounds.height / 2),
                  };
                  startWindowPointerTracking();
                }}
                onPointerUp={(event) => {
                  event.stopPropagation();
                  stopWindowPointerTracking();
                  commitPointerInteraction();
                }}
                onPointerCancel={(event) => {
                  event.stopPropagation();
                  stopWindowPointerTracking();
                  commitPointerInteraction();
                }}
              >
                <span className="memory-node-pulse" aria-hidden="true" />
                <span className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em]">
                  {node.kind}
                </span>
                <span className="mt-1 block text-sm font-semibold leading-5">{truncateLabel(node.label)}</span>
              </button>
            );
          })}
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
            {selectedScope === "global" ? "🌐 Shared" : "🔒 Private"}
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
