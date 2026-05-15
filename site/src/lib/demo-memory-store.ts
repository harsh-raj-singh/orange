import {
  demoMemoryGraphDetails,
  demoMemoryGraphEdges,
  demoMemoryGraphNodes,
  type DemoMemoryEdge,
  type DemoMemoryNode,
  type DemoMemoryNodeDetail,
  type DemoMemoryNodeType,
} from "@/lib/demo-memory-graph";

type DemoChatMessage = {
  role?: string;
  content?: unknown;
};

export type DemoConversationProfile = {
  name?: string;
  role?: string;
  company?: string;
  team?: string;
  project?: string;
  teamProject?: string;
};

export type CompleteDemoConversationInput = {
  sessionId?: string;
  trigger?: string;
  source?: string;
  profile?: DemoConversationProfile;
  messages?: DemoChatMessage[];
};

type DemoMemoryGraphSnapshot = {
  generatedAt: string;
  nodes: DemoMemoryNode[];
  edges: DemoMemoryEdge[];
};

type DemoMemoryStoreState = {
  nodes: Map<string, DemoMemoryNode>;
  edges: Map<string, DemoMemoryEdge>;
  details: Map<string, DemoMemoryNodeDetail>;
  completedSessions: Set<string>;
};

const globalStore = globalThis as typeof globalThis & {
  __orangeDemoMemoryStore?: DemoMemoryStoreState;
};

function cloneNode(node: DemoMemoryNode): DemoMemoryNode {
  return {
    ...node,
    metadata: { ...node.metadata },
  };
}

function cloneEdge(edge: DemoMemoryEdge): DemoMemoryEdge {
  return { ...edge };
}

function cloneDetail(detail: DemoMemoryNodeDetail): DemoMemoryNodeDetail {
  return {
    ...cloneNode(detail),
    detail: {
      title: detail.detail.title,
      body: detail.detail.body,
      evidence: [...detail.detail.evidence],
      relatedFiles: [...detail.detail.relatedFiles],
      nextActions: [...detail.detail.nextActions],
    },
  };
}

function createInitialState(): DemoMemoryStoreState {
  return {
    nodes: new Map(demoMemoryGraphNodes.map((node) => [node.id, cloneNode(node)])),
    edges: new Map(demoMemoryGraphEdges.map((edge) => [edge.id, cloneEdge(edge)])),
    details: new Map(
      Object.entries(demoMemoryGraphDetails).map(([id, detail]) => [
        id,
        cloneDetail(detail),
      ]),
    ),
    completedSessions: new Set(),
  };
}

function getState() {
  globalStore.__orangeDemoMemoryStore ??= createInitialState();
  return globalStore.__orangeDemoMemoryStore;
}

function normalizeIdPart(value: string) {
  return value
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "")
    .slice(0, 48);
}

function hashString(value: string) {
  let hash = 0;

  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }

  return hash.toString(36);
}

function messageContentToText(content: unknown): string {
  if (typeof content === "string") {
    return content;
  }

  if (Array.isArray(content)) {
    return content
      .map((part) => {
        if (typeof part === "string") {
          return part;
        }

        if (part && typeof part === "object" && "text" in part) {
          return String(part.text ?? "");
        }

        return "";
      })
      .filter(Boolean)
      .join(" ");
  }

  return "";
}

function compactText(value: string, fallback: string, maxLength = 180) {
  const text = value.replace(/\s+/g, " ").trim();

  if (!text) {
    return fallback;
  }

  return text.length <= maxLength ? text : `${text.slice(0, maxLength - 1)}...`;
}

function getConversationText(messages: DemoChatMessage[] = []) {
  return messages
    .map((message) => messageContentToText(message.content))
    .filter(Boolean)
    .join("\n");
}

function getLastMessageByRole(messages: DemoChatMessage[] = [], role: string) {
  return [...messages]
    .reverse()
    .find((message) => message.role === role && messageContentToText(message.content))
    ?.content;
}

function inferNodeType(text: string, fallback: DemoMemoryNodeType): DemoMemoryNodeType {
  const normalized = text.toLowerCase();

  if (/(error|bug|fail|broken|issue|problem|blocked|stuck)/.test(normalized)) {
    return "Problem";
  }

  if (/(fix|resolved|solution|answer|implement|ship|works)/.test(normalized)) {
    return "Solution";
  }

  if (/(try|attempt|tested|experiment|debug)/.test(normalized)) {
    return "Attempt";
  }

  return fallback;
}

function createMetadata(input: CompleteDemoConversationInput, createdAt: string) {
  const teamOrProject = input.profile?.teamProject ?? input.profile?.project ?? input.profile?.team;

  return {
    name: input.profile?.name,
    role: input.profile?.role,
    company: input.profile?.company,
    team: input.profile?.team ?? input.profile?.teamProject,
    project: input.profile?.project ?? input.profile?.teamProject,
    timestamp: createdAt,
    date: createdAt.slice(0, 10),
    sessionId: input.sessionId,
    source: input.source ?? "demo-chat",
    trigger: input.trigger ?? "conversation-complete",
    owner: teamOrProject ?? input.profile?.name ?? "demo-user",
    repo: "orange-demo",
    createdAt,
    status: "active" as const,
  };
}

function upsertNodeWithDetail(
  state: DemoMemoryStoreState,
  node: DemoMemoryNode,
  detail: DemoMemoryNodeDetail["detail"],
) {
  state.nodes.set(node.id, cloneNode(node));
  state.details.set(node.id, cloneDetail({ ...node, detail }));
}

function addEdge(state: DemoMemoryStoreState, edge: DemoMemoryEdge) {
  state.edges.set(edge.id, cloneEdge(edge));
}

export function getDemoMemoryGraphSnapshot(): DemoMemoryGraphSnapshot {
  const state = getState();

  return {
    generatedAt: new Date().toISOString(),
    nodes: [...state.nodes.values()].map(cloneNode),
    edges: [...state.edges.values()].map(cloneEdge),
  };
}

export function getDemoMemoryNodeDetailFromStore(nodeId: string) {
  const detail = getState().details.get(nodeId);
  return detail ? cloneDetail(detail) : null;
}

export function completeDemoConversation(input: CompleteDemoConversationInput) {
  const state = getState();
  const messages = input.messages ?? [];
  const conversationText = getConversationText(messages);
  const fallbackSessionId = hashString(
    JSON.stringify({
      profile: input.profile ?? {},
      messages: messages.map((message) => ({
        role: message.role,
        content: messageContentToText(message.content),
      })),
    }),
  );
  const sessionId = input.sessionId?.trim() || fallbackSessionId;
  const sessionKey = normalizeIdPart(sessionId) || fallbackSessionId;
  const sessionNodeId = `session-${sessionKey}`;

  if (state.completedSessions.has(sessionNodeId) || state.nodes.has(sessionNodeId)) {
    state.completedSessions.add(sessionNodeId);
    return getDemoMemoryGraphSnapshot();
  }

  const createdAt = new Date().toISOString();
  const metadata = createMetadata({ ...input, sessionId }, createdAt);
  const displayName = input.profile?.name ?? "Demo user";
  const project =
    input.profile?.teamProject ??
    input.profile?.project ??
    input.profile?.team ??
    "Orange demo";
  const userPrompt = compactText(
    messageContentToText(getLastMessageByRole(messages, "user")),
    "Captured a demo chat memory session.",
  );
  const assistantReply = compactText(
    messageContentToText(getLastMessageByRole(messages, "assistant")),
    "The assistant response was captured for later retrieval.",
  );

  const sessionNode: DemoMemoryNode = {
    id: sessionNodeId,
    label: `${displayName} chat session`,
    type: "Session",
    summary: compactText(
      `${displayName} completed a ${project} chat session: ${userPrompt}`,
      "Completed a demo chat session.",
      220,
    ),
    score: 0.9,
    metadata,
  };

  upsertNodeWithDetail(state, sessionNode, {
    title: sessionNode.label,
    body: compactText(conversationText, sessionNode.summary, 500),
    evidence: [
      `Session completed by ${displayName}.`,
      `Trigger: ${metadata.trigger}.`,
      `Source: ${metadata.source}.`,
    ],
    relatedFiles: [],
    nextActions: [
      "Use this session as retrieval context for similar demo conversations.",
      "Promote durable memories into a persistent graph backend.",
    ],
  });

  const memorySeed = [
    {
      suffix: "user-need",
      label: compactText(userPrompt, "User need", 64),
      type: inferNodeType(userPrompt, "Problem"),
      summary: userPrompt,
      labelEdge: "raised",
    },
    {
      suffix: "assistant-guidance",
      label: compactText(assistantReply, "Assistant guidance", 64),
      type: inferNodeType(assistantReply, "Solution"),
      summary: assistantReply,
      labelEdge: "answered",
    },
    {
      suffix: "project-context",
      label: `${project} context`,
      type: "Concept" as DemoMemoryNodeType,
      summary: compactText(
        conversationText,
        `Conversation context for ${project}.`,
        180,
      ),
      labelEdge: "contextualized",
    },
  ];

  memorySeed.forEach((item, index) => {
    const node: DemoMemoryNode = {
      id: `${item.type.toLowerCase()}-${sessionKey}-${item.suffix}`,
      label: item.label,
      type: item.type,
      summary: item.summary,
      score: 0.82 - index * 0.04,
      metadata,
    };

    upsertNodeWithDetail(state, node, {
      title: node.label,
      body: node.summary,
      evidence: [
        `Derived from ${displayName}'s completed demo conversation.`,
        `Session id: ${sessionId}.`,
      ],
      relatedFiles: [],
      nextActions: ["Retrieve when future chat messages overlap this wording."],
    });

    addEdge(state, {
      id: `edge-${sessionKey}-${item.suffix}`,
      source: sessionNode.id,
      target: node.id,
      label: item.labelEdge,
      strength: 0.78 - index * 0.05,
    });
  });

  state.completedSessions.add(sessionNodeId);
  return getDemoMemoryGraphSnapshot();
}
