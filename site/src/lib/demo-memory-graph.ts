export type DemoMemoryNodeType =
  | "Insight"
  | "Problem"
  | "Solution"
  | "Attempt"
  | "Artifact"
  | "Concept"
  | "Session";

export type DemoMemoryNode = {
  id: string;
  label: string;
  type: DemoMemoryNodeType;
  summary: string;
  score?: number;
  metadata: {
    name?: string;
    role?: string;
    company?: string;
    team?: string;
    project?: string;
    timestamp?: string;
    date?: string;
    sessionId?: string;
    source?: string;
    trigger?: string;
    owner?: string;
    repo?: string;
    createdAt: string;
    status?: "open" | "resolved" | "failed" | "active";
    outcome?: "resolved" | "exploratory" | "partial" | "abandoned";
    tags?: string[];
  };
};

export type DemoMemoryEdge = {
  id: string;
  source: string;
  target: string;
  label: string;
  strength: number;
};

export type DemoMemoryNodeDetail = DemoMemoryNode & {
  detail: {
    title: string;
    body: string;
    evidence: string[];
    relatedFiles: string[];
    nextActions: string[];
    what?: string;
    why?: string | null;
    how?: string | null;
    outcome?: string;
    tags?: string[];
  };
};

export const demoMemoryGraphNodes = [
  {
    id: "session-2026-05-15",
    label: "Checkout flow debugging session",
    type: "Session",
    summary:
      "A Cursor and Claude Code pair session investigating why checkout submissions intermittently failed.",
    score: 0.96,
    metadata: {
      owner: "frontend-platform",
      repo: "orange-demo",
      createdAt: "2026-05-15T09:10:00.000Z",
      status: "active",
    },
  },
  {
    id: "problem-cors-preflight",
    label: "CORS preflight rejected",
    type: "Problem",
    summary:
      "OPTIONS requests returned 405 because API middleware was mounted after route registration.",
    score: 0.91,
    metadata: {
      owner: "api-platform",
      repo: "orange-demo",
      createdAt: "2026-05-15T09:18:00.000Z",
      status: "resolved",
    },
  },
  {
    id: "attempt-origin-list",
    label: "Expanded allowed origins",
    type: "Attempt",
    summary:
      "Adding localhost aliases to the origin list did not change preflight behavior.",
    score: 0.72,
    metadata: {
      owner: "api-platform",
      repo: "orange-demo",
      createdAt: "2026-05-15T09:31:00.000Z",
      status: "failed",
    },
  },
  {
    id: "solution-middleware-order",
    label: "Move middleware before routes",
    type: "Solution",
    summary:
      "Register CORSMiddleware before route handlers so OPTIONS is handled globally.",
    score: 0.94,
    metadata: {
      owner: "api-platform",
      repo: "orange-demo",
      createdAt: "2026-05-15T09:45:00.000Z",
      status: "resolved",
    },
  },
  {
    id: "artifact-api-router",
    label: "api/server.ts",
    type: "Artifact",
    summary:
      "Server bootstrap file where middleware and routers are composed.",
    score: 0.83,
    metadata: {
      owner: "api-platform",
      repo: "orange-demo",
      createdAt: "2026-05-15T09:46:00.000Z",
      status: "active",
    },
  },
  {
    id: "concept-preflight",
    label: "Browser preflight",
    type: "Concept",
    summary:
      "Browsers send OPTIONS before cross-origin requests that use non-simple headers or methods.",
    score: 0.88,
    metadata: {
      repo: "orange-demo",
      createdAt: "2026-05-15T09:50:00.000Z",
      status: "active",
    },
  },
] satisfies DemoMemoryNode[];

export const demoMemoryGraphEdges = [
  {
    id: "edge-session-problem",
    source: "session-2026-05-15",
    target: "problem-cors-preflight",
    label: "observed",
    strength: 0.92,
  },
  {
    id: "edge-problem-attempt",
    source: "problem-cors-preflight",
    target: "attempt-origin-list",
    label: "tested",
    strength: 0.69,
  },
  {
    id: "edge-attempt-solution",
    source: "attempt-origin-list",
    target: "solution-middleware-order",
    label: "led_to",
    strength: 0.78,
  },
  {
    id: "edge-solution-artifact",
    source: "solution-middleware-order",
    target: "artifact-api-router",
    label: "changed",
    strength: 0.86,
  },
  {
    id: "edge-problem-concept",
    source: "problem-cors-preflight",
    target: "concept-preflight",
    label: "explained_by",
    strength: 0.81,
  },
] satisfies DemoMemoryEdge[];

export const demoMemoryGraphDetails = {
  "session-2026-05-15": {
    ...demoMemoryGraphNodes[0],
    detail: {
      title: "Checkout flow debugging session",
      body: "The session captured the failed request, the first unsuccessful configuration change, and the final middleware-order fix.",
      evidence: [
        "Network trace showed OPTIONS failing before the POST handler ran.",
        "The same endpoint succeeded when called server-side without browser CORS enforcement.",
      ],
      relatedFiles: ["api/server.ts", "web/components/checkout-form.tsx"],
      nextActions: [
        "Add a regression test for OPTIONS on checkout routes.",
        "Link future CORS incidents to this session neighborhood.",
      ],
    },
  },
  "problem-cors-preflight": {
    ...demoMemoryGraphNodes[1],
    detail: {
      title: "CORS preflight rejected",
      body: "The core problem was route ordering, not the allow-list itself. Browser preflight traffic never reached the middleware that should have answered it.",
      evidence: [
        "OPTIONS /api/checkout returned 405.",
        "Server logs showed no checkout handler invocation for the failed preflight.",
      ],
      relatedFiles: ["api/server.ts"],
      nextActions: [
        "Keep CORS and request-wide middleware at the top of server setup.",
        "Surface this node when a new issue mentions OPTIONS, CORS, or preflight.",
      ],
    },
  },
  "attempt-origin-list": {
    ...demoMemoryGraphNodes[2],
    detail: {
      title: "Expanded allowed origins",
      body: "The team added localhost variants to the origin list, which was plausible but did not address the 405 response path.",
      evidence: [
        "Allowed origins included localhost, 127.0.0.1, and preview hostnames.",
        "The response code stayed 405 after the configuration change.",
      ],
      relatedFiles: ["api/config.ts"],
      nextActions: [
        "Check status code and handler path before broadening allow-lists.",
        "Mark repeated origin-list changes as low confidence for this symptom.",
      ],
    },
  },
  "solution-middleware-order": {
    ...demoMemoryGraphNodes[3],
    detail: {
      title: "Move middleware before routes",
      body: "Registering CORS middleware before route setup allowed the framework to answer OPTIONS consistently for every API route.",
      evidence: [
        "OPTIONS /api/checkout returned 204 after reordering.",
        "The checkout POST succeeded from the browser after the preflight passed.",
      ],
      relatedFiles: ["api/server.ts"],
      nextActions: [
        "Document server bootstrap ordering in the API README.",
        "Add a smoke test for one protected and one public API route.",
      ],
    },
  },
  "artifact-api-router": {
    ...demoMemoryGraphNodes[4],
    detail: {
      title: "api/server.ts",
      body: "The artifact anchors the memory graph to the file where middleware order is controlled.",
      evidence: [
        "The final diff moved middleware registration above router mounting.",
        "No checkout component changes were needed for the successful fix.",
      ],
      relatedFiles: ["api/server.ts"],
      nextActions: [
        "Attach future server bootstrap changes to this artifact node.",
        "Expose recent incidents for this file in agent context.",
      ],
    },
  },
  "concept-preflight": {
    ...demoMemoryGraphNodes[5],
    detail: {
      title: "Browser preflight",
      body: "The concept node gives agents a reusable explanation for why browser requests can fail before application handlers run.",
      evidence: [
        "The failing request included Authorization and Content-Type headers.",
        "A server-side fetch bypassed browser preflight behavior.",
      ],
      relatedFiles: ["docs/api/cors.md"],
      nextActions: [
        "Prefer concept retrieval when new sessions mention browser-only failures.",
        "Keep the explanation short enough for compact agent context.",
      ],
    },
  },
} satisfies Record<string, DemoMemoryNodeDetail>;

export function getDemoMemoryGraph() {
  return {
    generatedAt: "2026-05-15T10:00:00.000Z",
    nodes: demoMemoryGraphNodes,
    edges: demoMemoryGraphEdges,
  };
}

export function getDemoMemoryNodeDetail(nodeId: string) {
  if (nodeId in demoMemoryGraphDetails) {
    return demoMemoryGraphDetails[nodeId as keyof typeof demoMemoryGraphDetails];
  }

  return null;
}
