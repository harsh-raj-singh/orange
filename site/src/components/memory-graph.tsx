"use client";

import { useMemo, useRef, useState } from "react";

type MemoryNode = {
  id: string;
  label: string;
  kind: "Problem" | "Attempt" | "Solution" | "Artifact" | "Concept" | "Session";
  x: number;
  y: number;
  summary: string;
  detail: string;
};

const memoryNodes: MemoryNode[] = [
  {
    id: "cors",
    label: "CORS preflight fails",
    kind: "Problem",
    x: 18,
    y: 28,
    summary: "OPTIONS requests returned 405 after a router refactor.",
    detail: "Orange keeps the failure mode connected to the final middleware ordering fix, so a later agent can skip repeating origin-list changes.",
  },
  {
    id: "middleware",
    label: "Middleware ordering",
    kind: "Concept",
    x: 43,
    y: 18,
    summary: "FastAPI middleware must wrap routes before handlers are mounted.",
    detail: "This concept links several sessions where registration order changed runtime behavior without changing endpoint code.",
  },
  {
    id: "allowed-origins",
    label: "Origin list edit",
    kind: "Attempt",
    x: 28,
    y: 62,
    summary: "Expanded allowed origins, but preflight still failed.",
    detail: "A stored failed attempt is useful context because it tells the next engineer which plausible fix already burned time.",
  },
  {
    id: "move-cors",
    label: "Move CORSMiddleware",
    kind: "Solution",
    x: 62,
    y: 48,
    summary: "Register CORSMiddleware before include_router.",
    detail: "The winning solution is linked to the problem, failed attempt, and code artifact that changed in the final patch.",
  },
  {
    id: "server-py",
    label: "server.py patch",
    kind: "Artifact",
    x: 78,
    y: 22,
    summary: "Changed app construction order in the API entrypoint.",
    detail: "Artifact nodes let Orange return exact files and implementation surfaces instead of only semantic summaries.",
  },
  {
    id: "session",
    label: "Debug session",
    kind: "Session",
    x: 73,
    y: 70,
    summary: "Claude Code trace from reproduction to patch verification.",
    detail: "Session nodes preserve who participated, when the work happened, and the compact transcript that seeded the graph.",
  },
];

const links = [
  ["cors", "middleware"],
  ["cors", "allowed-origins"],
  ["cors", "move-cors"],
  ["middleware", "server-py"],
  ["move-cors", "server-py"],
  ["move-cors", "session"],
  ["allowed-origins", "session"],
] as const;

const kindClass: Record<MemoryNode["kind"], string> = {
  Problem: "border-[#c5551c] bg-[#fff8ec] text-[#8f3b14]",
  Attempt: "border-[#c3a46b] bg-[#fffdf6] text-[#6d5421]",
  Solution: "border-[#2f6f5e] bg-[#f1faf5] text-[#205545]",
  Artifact: "border-[#5f746b] bg-[#f7f9f6] text-[#344740]",
  Concept: "border-[#839a8d] bg-white text-[#40554b]",
  Session: "border-[#24352d] bg-[#f6f7f4] text-[#24352d]",
};

export default function MemoryGraph() {
  const [nodes, setNodes] = useState(memoryNodes);
  const [selectedId, setSelectedId] = useState("cors");
  const graphRef = useRef<HTMLDivElement>(null);
  const dragRef = useRef<{ id: string; dx: number; dy: number } | null>(null);

  const selectedNode = useMemo(
    () => nodes.find((node) => node.id === selectedId) ?? nodes[0],
    [nodes, selectedId],
  );

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

  return (
    <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_320px]">
      <div
        ref={graphRef}
        className="relative min-h-[420px] overflow-hidden rounded-lg border border-[#24352d]/10 bg-[#fbfaf5] shadow-[0_24px_70px_rgba(36,53,45,0.12)] touch-none sm:min-h-[500px]"
        onPointerMove={(event) => moveNode(event.clientX, event.clientY)}
        onPointerUp={() => {
          dragRef.current = null;
        }}
        onPointerLeave={() => {
          dragRef.current = null;
        }}
      >
        <svg className="absolute inset-0 h-full w-full" role="presentation">
          {links.map(([from, to]) => {
            const start = nodes.find((node) => node.id === from);
            const end = nodes.find((node) => node.id === to);

            if (!start || !end) {
              return null;
            }

            return (
              <line
                key={`${from}-${to}`}
                x1={`${start.x}%`}
                y1={`${start.y}%`}
                x2={`${end.x}%`}
                y2={`${end.y}%`}
                stroke="#9aa79d"
                strokeOpacity="0.46"
                strokeWidth="1.5"
              />
            );
          })}
        </svg>

        <div className="absolute left-5 top-5 rounded-md border border-[#24352d]/10 bg-white/88 px-3 py-2 shadow-sm backdrop-blur">
          <p className="font-mono text-xs font-semibold uppercase tracking-[0.18em] text-[#c5551c]">
            Live neighborhood
          </p>
        </div>

        {nodes.map((node) => {
          const isSelected = node.id === selectedId;

          return (
            <button
              key={node.id}
              type="button"
              className={`absolute w-[9.75rem] -translate-x-1/2 -translate-y-1/2 cursor-grab rounded-lg border px-3 py-3 text-left shadow-[0_16px_38px_rgba(36,53,45,0.12)] transition active:cursor-grabbing ${kindClass[node.kind]} ${
                isSelected ? "ring-2 ring-[#c5551c] ring-offset-2 ring-offset-[#fbfaf5]" : "hover:-translate-y-[calc(50%+2px)]"
              }`}
              style={{ left: `${node.x}%`, top: `${node.y}%` }}
              onClick={() => setSelectedId(node.id)}
              onPointerDown={(event) => {
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

      <aside className="rounded-lg border border-[#24352d]/10 bg-white p-5 shadow-[0_18px_46px_rgba(36,53,45,0.10)]">
        <p className="font-mono text-xs font-semibold uppercase tracking-[0.2em] text-[#2f6f5e]">
          Selected node
        </p>
        <h3 className="mt-4 text-2xl font-semibold text-[#161b18]">{selectedNode.label}</h3>
        <p className="mt-2 font-mono text-sm text-[#c5551c]">{selectedNode.kind}</p>
        <p className="mt-5 text-sm leading-6 text-[#536057]">{selectedNode.summary}</p>
        <div className="mt-5 rounded-md bg-[#f7f3e8] p-4 text-sm leading-6 text-[#3f4b44]">
          {selectedNode.detail}
        </div>
      </aside>
    </div>
  );
}
