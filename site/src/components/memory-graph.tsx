"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type MemoryNode = {
  id: string;
  label: string;
  kind: "Problem" | "Attempt" | "Solution" | "Artifact" | "Concept" | "Session";
  x: number;
  y: number;
  summary: string;
  score?: number;
  metadata?: {
    owner?: string;
    repo?: string;
    createdAt?: string;
    status?: string;
  };
  detailTitle?: string;
  detailBody?: string;
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

const memoryNodes: MemoryNode[] = [
  {
    id: "cors",
    label: "CORS preflight fails",
    kind: "Problem",
    x: 18,
    y: 28,
    summary: "OPTIONS requests returned 405 after a router refactor.",
    detailBody: "Orange keeps the failure mode connected to the final middleware ordering fix, so a later agent can skip repeating origin-list changes.",
  },
  {
    id: "middleware",
    label: "Middleware ordering",
    kind: "Concept",
    x: 43,
    y: 18,
    summary: "FastAPI middleware must wrap routes before handlers are mounted.",
    detailBody: "This concept links several sessions where registration order changed runtime behavior without changing endpoint code.",
  },
  {
    id: "allowed-origins",
    label: "Origin list edit",
    kind: "Attempt",
    x: 28,
    y: 62,
    summary: "Expanded allowed origins, but preflight still failed.",
    detailBody: "A stored failed attempt is useful context because it tells the next engineer which plausible fix already burned time.",
  },
  {
    id: "move-cors",
    label: "Move CORSMiddleware",
    kind: "Solution",
    x: 62,
    y: 48,
    summary: "Register CORSMiddleware before include_router.",
    detailBody: "The winning solution is linked to the problem, failed attempt, and code artifact that changed in the final patch.",
  },
  {
    id: "server-py",
    label: "server.py patch",
    kind: "Artifact",
    x: 78,
    y: 22,
    summary: "Changed app construction order in the API entrypoint.",
    detailBody: "Artifact nodes let Orange return exact files and implementation surfaces instead of only semantic summaries.",
  },
  {
    id: "session",
    label: "Debug session",
    kind: "Session",
    x: 73,
    y: 70,
    summary: "Claude Code trace from reproduction to patch verification.",
    detailBody: "Session nodes preserve who participated, when the work happened, and the compact transcript that seeded the graph.",
  },
];

const fallbackEdges: MemoryEdge[] = [
  { id: "cors-middleware", source: "cors", target: "middleware", strength: 0.78 },
  { id: "cors-allowed-origins", source: "cors", target: "allowed-origins", strength: 0.68 },
  { id: "cors-move-cors", source: "cors", target: "move-cors", strength: 0.92 },
  { id: "middleware-server-py", source: "middleware", target: "server-py", strength: 0.72 },
  { id: "move-cors-server-py", source: "move-cors", target: "server-py", strength: 0.86 },
  { id: "move-cors-session", source: "move-cors", target: "session", strength: 0.8 },
  { id: "allowed-origins-session", source: "allowed-origins", target: "session", strength: 0.62 },
];

const kindClass: Record<MemoryNode["kind"], string> = {
  Problem: "border-[#c5551c] bg-[#fff8ec] text-[#8f3b14]",
  Attempt: "border-[#c3a46b] bg-[#fffdf6] text-[#6d5421]",
  Solution: "border-[#2f6f5e] bg-[#f1faf5] text-[#205545]",
  Artifact: "border-[#5f746b] bg-[#f7f9f6] text-[#344740]",
  Concept: "border-[#839a8d] bg-white text-[#40554b]",
  Session: "border-[#24352d] bg-[#f6f7f4] text-[#24352d]",
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function asString(value: unknown) {
  return typeof value === "string" ? value : undefined;
}

function asStringArray(value: unknown) {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === "string") : undefined;
}

function asNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : undefined;
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
      }
    : existing?.metadata;
  const detailBody = asString(value.detail) ?? asString(detail?.body) ?? existing?.detailBody;

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
  const [nodes, setNodes] = useState(memoryNodes);
  const [edges, setEdges] = useState<MemoryEdge[]>(fallbackEdges);
  const [selectedId, setSelectedId] = useState("cors");
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [detailLoadingId, setDetailLoadingId] = useState<string | null>(null);
  const [newNodeIds, setNewNodeIds] = useState<Set<string>>(new Set());
  const [viewport, setViewport] = useState({ scale: 1, x: 0, y: 0 });
  const graphRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);
  const panRef = useRef<{ x: number; y: number; startX: number; startY: number } | null>(null);
  const seenNodeIdsRef = useRef(new Set(memoryNodes.map((node) => node.id)));

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedId) ?? nodes[0],
    [nodes, selectedId],
  );
  const selectedDate = formatDate(selectedNode?.metadata?.createdAt);

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
      const response = await fetch("/api/demo/memory-graph", {
        cache: "no-store",
      });

      if (!response.ok) {
        throw new Error(`Graph request failed: ${response.status}`);
      }

      const graph: unknown = await response.json();

      if (!isRecord(graph)) {
        return;
      }

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

        return nextNodes.length > 0 ? resolveOverlaps(nextNodes) : current;
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
  }, [resolveOverlaps]);

  useEffect(() => {
    const initialRefresh = window.setTimeout(() => {
      void fetchGraph(false);
    }, 0);

    const handleGraphUpdate = () => {
      void fetchGraph();
    };
    const interval = window.setInterval(() => {
      void fetchGraph();
    }, 6000);

    window.addEventListener("orange-memory-graph-updated", handleGraphUpdate);

    return () => {
      window.clearTimeout(initialRefresh);
      window.clearInterval(interval);
      window.removeEventListener("orange-memory-graph-updated", handleGraphUpdate);
    };
  }, [fetchGraph]);

  async function selectNode(node: MemoryNode) {
    setSelectedId(node.id);

    if (node.detailBody || detailLoadingId === node.id) {
      return;
    }

    setDetailLoadingId(node.id);

    try {
      const response = await fetch(`/api/demo/memory-graph/${encodeURIComponent(node.id)}`, {
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
    const bounds = graphRef.current?.getBoundingClientRect();

    if (!drag || !bounds) {
      return;
    }

    const x = ((clientX - bounds.left - drag.dx) / bounds.width) * 100;
    const y = ((clientY - bounds.top - drag.dy) / bounds.height) * 100;

    setNodes((current) =>
      current.map((node) =>
        node.id === drag.id
          ? {
              ...node,
              x: Math.min(88, Math.max(12, x)),
              y: Math.min(84, Math.max(14, y)),
            }
          : node,
      ),
    );
  }

  function movePan(clientX: number, clientY: number) {
    const pan = panRef.current;
    if (!pan) {
      return;
    }
    setViewport((current) => ({
      ...current,
      x: pan.x + clientX - pan.startX,
      y: pan.y + clientY - pan.startY,
    }));
  }

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
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
            x: viewport.x,
            y: viewport.y,
            startX: event.clientX,
            startY: event.clientY,
          };
        }}
        onPointerMove={(event) => {
          moveNode(event.clientX, event.clientY);
          movePan(event.clientX, event.clientY);
        }}
        onPointerUp={() => {
          dragRef.current = null;
          panRef.current = null;
        }}
        onPointerLeave={() => {
          dragRef.current = null;
          panRef.current = null;
        }}
      >
        <div
          className="absolute inset-0"
          style={{
            transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.scale})`,
            transformOrigin: "50% 50%",
          }}
        >
          <svg className="absolute inset-0 h-full w-full" role="presentation">
            {edges.map((edge) => {
              const start = nodes.find((node) => node.id === edge.source);
              const end = nodes.find((node) => node.id === edge.target);

              if (!start || !end) {
                return null;
              }

              return (
                <g className="group" key={edge.id}>
                  <line
                    x1={`${start.x}%`}
                    y1={`${start.y}%`}
                    x2={`${end.x}%`}
                    y2={`${end.y}%`}
                    stroke="#9aa79d"
                    strokeOpacity={String(0.32 + (edge.strength ?? 0.7) * 0.28)}
                    strokeWidth={String(1 + (edge.strength ?? 0.7))}
                  />
                  {edge.label ? (
                    <text
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

        <div className="absolute left-5 top-5 rounded-md border border-[#24352d]/10 bg-white/88 px-3 py-2 shadow-sm backdrop-blur">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#c5551c]">
            Live neighborhood
          </p>
          <p className="mt-1 text-xs text-[#536057]">
            {nodes.length} nodes {isRefreshing ? "syncing" : "linked"}
          </p>
        </div>

          {nodes.map((node) => {
            const isSelected = node.id === selectedNode?.id;
            const isNew = newNodeIds.has(node.id);

            return (
              <button
                key={node.id}
                type="button"
                className={`absolute w-[9.75rem] -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-lg border px-3 py-3 text-left shadow-[0_16px_38px_rgba(36,53,45,0.12)] transition-[opacity,transform,box-shadow] duration-500 active:cursor-grabbing ${kindClass[node.kind]} ${
                  isSelected ? "ring-2 ring-[#c5551c] ring-offset-2 ring-offset-[#fbfaf5]" : "hover:-translate-y-[calc(50%+2px)]"
                } ${isNew ? "scale-0 opacity-0" : "scale-100 opacity-100"}`}
                style={{ left: `${node.x}%`, top: `${node.y}%` }}
                onClick={() => {
                  void selectNode(node);
                }}
                onPointerDown={(event) => {
                  event.stopPropagation();
                  const bounds = graphRef.current?.getBoundingClientRect();

                  if (!bounds) {
                    return;
                  }

                  event.currentTarget.setPointerCapture(event.pointerId);
                  setSelectedId(node.id);
                  dragRef.current = {
                    id: node.id,
                    dx: event.clientX - (bounds.left + (node.x / 100) * bounds.width),
                    dy: event.clientY - (bounds.top + (node.y / 100) * bounds.height),
                  };
                }}
              >
                <span className="font-mono text-[0.68rem] font-semibold uppercase tracking-[0.14em]">
                  {node.kind}
                </span>
                <span className="mt-1 block text-sm font-semibold leading-5">{node.label}</span>
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
        </div>
        <p className="mt-5 text-sm leading-6 text-[#536057]">{selectedNode?.summary}</p>
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
        {selectedNode?.metadata || selectedDate ? (
          <dl className="mt-5 grid gap-3 text-sm text-[#536057]">
            {selectedNode.metadata?.owner ? (
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
