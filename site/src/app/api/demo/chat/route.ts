import { NextResponse } from "next/server";
import { orangeBackendFetch } from "@/lib/orange-backend";

const OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions";
const DEFAULT_OPENAI_MODEL = "gpt-5.4-nano";
const DEFAULT_TIMEOUT_MS = 30000;

type DemoProfile = {
  name?: string;
  email?: string;
  role?: string;
  company?: string;
  teamProject?: string;
};

type IncomingMessage = {
  role?: unknown;
  content?: unknown;
};

type DemoChatRequest = {
  profile?: DemoProfile;
  messages?: unknown;
  sessionId?: string;
  model?: string;
  temperature?: number;
  max_tokens?: number;
  contribute_to_global?: boolean;
};

type MemoryMatch = {
  id: string;
  label: string;
  node_type: string;
  similarity_score: number;
  scope?: "user" | "global";
};

type PingContextResponse = {
  matched_nodes?: Array<{
    node_type?: string;
    similarity_score?: number;
    source?: string;
    scope?: string;
    node_data?: {
      canonical_label?: string;
      description?: string;
      in_depth_summary?: string;
      error_code?: string | null;
      tech_stack?: string[];
      scope?: string;
    };
    neighborhood?: Record<string, unknown>;
  }>;
  node_ids_used?: string[];
};

type OpenAIChatResponse = {
  choices?: Array<{
    message?: {
      content?: unknown;
    };
  }>;
  error?: {
    message?: string;
  };
};

function normalizeScope(value: unknown): "user" | "global" {
  return value === "global" || value === "shared" ? "global" : "user";
}

function normalizeMessage(message: IncomingMessage) {
  const role = message.role === "assistant" ? "assistant" : "user";
  const content = typeof message.content === "string" ? message.content.trim() : "";

  if (!content) {
    return null;
  }

  return { role, content };
}

function createSystemPrompt(profile?: DemoProfile, memoryContext?: string) {
  const name = profile?.name?.trim() || "the user";
  const role = profile?.role?.trim() || "developer";
  const company = profile?.company?.trim() || "their company";
  const teamProject = profile?.teamProject?.trim() || "their current project";

  const lines = [
    "You are Orange, a concise developer memory fabric demo.",
    "Help the user reason through engineering work in a way that would create useful future memory.",
    "Prefer concrete causes, decisions, failed attempts, next actions, and file or system surfaces when the user gives them.",
    `User metadata: name=${name}; role=${role}; company=${company}; team_or_project=${teamProject}.`,
  ];

  if (memoryContext) {
    lines.push(`Memory context:\n${memoryContext}`);
  }

  return lines.join("\n");
}

function buildOpenAIRequestBody(
  body: DemoChatRequest,
  messages: Array<{ role: "user" | "assistant"; content: string }>,
  memoryContext?: string,
) {
  const model = process.env.OPENAI_CHAT_MODEL ?? body.model ?? DEFAULT_OPENAI_MODEL;
  const tokenLimit = body.max_tokens ?? 512;
  const requestBody: Record<string, unknown> = {
    model,
    messages: [
      {
        role: "system",
        content: createSystemPrompt(body.profile, memoryContext),
      },
      ...messages,
    ],
    stream: true,
  };

  if (model.startsWith("gpt-5")) {
    requestBody.max_completion_tokens = tokenLimit;
  } else {
    requestBody.max_tokens = tokenLimit;
    requestBody.temperature = body.temperature ?? 0.7;
  }

  return requestBody;
}

function buildMemoryContext(memory?: PingContextResponse | null) {
  const nodes = memory?.matched_nodes ?? [];
  const nodeIds = memory?.node_ids_used ?? [];

  const matches = nodes.map((node, index): MemoryMatch => {
    const label = node.node_data?.canonical_label ?? `${node.node_type ?? "Memory"} ${index + 1}`;

    return {
      id: nodeIds[index] ?? label,
      label,
      node_type: node.node_type ?? "Memory",
      similarity_score: node.similarity_score ?? 0,
      scope: normalizeScope(node.scope ?? node.source ?? node.node_data?.scope),
    };
  });

  const context = nodes
    .map((node, index) => {
      const label = node.node_data?.canonical_label ?? `Memory ${index + 1}`;
      const scope = normalizeScope(node.scope ?? node.source ?? node.node_data?.scope);
      const description =
        node.node_data?.description ??
        node.node_data?.in_depth_summary ??
        "No stored description.";
      const neighborhood = node.neighborhood
        ? `\nNeighborhood: ${JSON.stringify(node.neighborhood).slice(0, 900)}`
        : "";

      return `- ${label} (${node.node_type}, ${scope}, score=${node.similarity_score}): ${description}${neighborhood}`;
    })
    .join("\n");

  return {
    context,
    matches,
    nodeIds,
  };
}

async function fetchMemoryContext(body: DemoChatRequest, latestUserMessage: string) {
  try {
    const memory = await orangeBackendFetch<PingContextResponse>("/demo/ping_context", {
      method: "POST",
      body: {
        profile: body.profile,
        query: latestUserMessage,
        source: "cursor",
        min_score: 0.7,
        contribute_to_global: body.contribute_to_global ?? true,
        scope: body.contribute_to_global === false ? "user" : "both",
      },
    });
    return buildMemoryContext(memory);
  } catch (error) {
    console.warn("orange_backend_ping_failed", error);
    return buildMemoryContext(null);
  }
}

function sse(event: string, data: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(data)}\n\n`;
}

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const apiKey = process.env.OPENAI_API_KEY;

  if (!apiKey) {
    return NextResponse.json(
      { error: "OPENAI_API_KEY is not configured on the server." },
      { status: 503 },
    );
  }

  let body: DemoChatRequest;

  try {
    body = (await request.json()) as DemoChatRequest;
  } catch {
    return NextResponse.json(
      { error: "Chat payload must be valid JSON." },
      { status: 400 },
    );
  }

  if (!Array.isArray(body.messages)) {
    return NextResponse.json(
      { error: "Chat payload requires a messages array." },
      { status: 400 },
    );
  }

  const messages = body.messages
    .map((message) => normalizeMessage(message as IncomingMessage))
    .filter((message): message is { role: "user" | "assistant"; content: string } =>
      Boolean(message),
    );

  if (messages.length === 0) {
    return NextResponse.json(
      { error: "Chat payload requires at least one non-empty message." },
      { status: 400 },
    );
  }

  const latestUserMessage = [...messages].reverse().find((message) => message.role === "user")?.content ?? "";
  const memory = await fetchMemoryContext(body, latestUserMessage);

  const timeoutMs = Number(process.env.OPENAI_CHAT_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let upstreamResponse: Response;

  try {
    upstreamResponse = await fetch(OPENAI_CHAT_COMPLETIONS_URL, {
      method: "POST",
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify(buildOpenAIRequestBody(body, messages, memory.context)),
    });
  } catch (error) {
    const isAbort =
      error instanceof Error &&
      (error.name === "AbortError" || error.message.toLowerCase().includes("aborted"));

    return NextResponse.json(
      {
        error: isAbort
          ? "OpenAI chat timed out before returning a response."
          : "OpenAI chat request failed before a response was returned.",
      },
      { status: isAbort ? 504 : 502 },
    );
  } finally {
    clearTimeout(timeout);
  }

  if (!upstreamResponse.ok) {
    const responseText = await upstreamResponse.text();
    let responseBody: unknown = responseText;

    try {
      responseBody = responseText ? JSON.parse(responseText) : {};
    } catch {
      responseBody = { error: responseText };
    }
    return NextResponse.json(
      {
        error:
          typeof responseBody === "object" &&
          responseBody !== null &&
          "error" in responseBody &&
          typeof (responseBody as OpenAIChatResponse).error?.message === "string"
            ? (responseBody as OpenAIChatResponse).error?.message
            : "OpenAI chat request failed.",
      },
      { status: upstreamResponse.status },
    );
  }

  const encoder = new TextEncoder();
  const decoder = new TextDecoder();
  let fullMessage = "";

  const stream = new ReadableStream({
    async start(controller) {
      controller.enqueue(
        encoder.encode(
          sse("memory", {
            memory_used: memory.matches.length > 0,
            node_ids: memory.nodeIds,
            matches: memory.matches,
          }),
        ),
      );

      const reader = upstreamResponse.body?.getReader();
      if (!reader) {
        controller.enqueue(
          encoder.encode(
            sse("done", {
              message: "",
              sessionId: body.sessionId,
              memory_used: memory.matches.length > 0,
              node_ids: memory.nodeIds,
              matches: memory.matches,
            }),
          ),
        );
        controller.close();
        return;
      }

      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const trimmed = line.trim();
          if (!trimmed.startsWith("data:")) {
            continue;
          }

          const payload = trimmed.slice(5).trim();
          if (!payload || payload === "[DONE]") {
            continue;
          }

          try {
            const chunk = JSON.parse(payload) as {
              choices?: Array<{ delta?: { content?: string } }>;
            };
            const delta = chunk.choices?.[0]?.delta?.content;
            if (delta) {
              fullMessage += delta;
              controller.enqueue(encoder.encode(sse("delta", { text: delta })));
            }
          } catch {
            // Ignore malformed upstream stream fragments.
          }
        }
      }

      controller.enqueue(
        encoder.encode(
          sse("done", {
            message: fullMessage,
            sessionId: body.sessionId,
            memory_used: memory.matches.length > 0,
            node_ids: memory.nodeIds,
            matches: memory.matches,
          }),
        ),
      );
      controller.close();
    },
  });

  return new Response(stream, {
    headers: {
      "Content-Type": "text/event-stream; charset=utf-8",
      "Cache-Control": "no-cache, no-transform",
      Connection: "keep-alive",
    },
  });
}
