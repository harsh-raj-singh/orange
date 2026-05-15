import { NextResponse } from "next/server";

const OPENAI_CHAT_COMPLETIONS_URL = "https://api.openai.com/v1/chat/completions";
const DEFAULT_OPENAI_MODEL = "gpt-5.4-nano";
const DEFAULT_TIMEOUT_MS = 30000;

type DemoProfile = {
  name?: string;
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

function normalizeMessage(message: IncomingMessage) {
  const role = message.role === "assistant" ? "assistant" : "user";
  const content = typeof message.content === "string" ? message.content.trim() : "";

  if (!content) {
    return null;
  }

  return { role, content };
}

function createSystemPrompt(profile?: DemoProfile) {
  const name = profile?.name?.trim() || "the user";
  const role = profile?.role?.trim() || "developer";
  const company = profile?.company?.trim() || "their company";
  const teamProject = profile?.teamProject?.trim() || "their current project";

  return [
    "You are Orange, a concise developer memory fabric demo.",
    "Help the user reason through engineering work in a way that would create useful future memory.",
    "Prefer concrete causes, decisions, failed attempts, next actions, and file or system surfaces when the user gives them.",
    `User metadata: name=${name}; role=${role}; company=${company}; team_or_project=${teamProject}.`,
  ].join("\n");
}

function buildOpenAIRequestBody(body: DemoChatRequest, messages: Array<{ role: "user" | "assistant"; content: string }>) {
  const model = process.env.OPENAI_CHAT_MODEL ?? body.model ?? DEFAULT_OPENAI_MODEL;
  const tokenLimit = body.max_tokens ?? 512;
  const requestBody: Record<string, unknown> = {
    model,
    messages: [
      {
        role: "system",
        content: createSystemPrompt(body.profile),
      },
      ...messages,
    ],
  };

  if (model.startsWith("gpt-5")) {
    requestBody.max_completion_tokens = tokenLimit;
  } else {
    requestBody.max_tokens = tokenLimit;
    requestBody.temperature = body.temperature ?? 0.7;
  }

  return requestBody;
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
      body: JSON.stringify(buildOpenAIRequestBody(body, messages)),
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

  const responseText = await upstreamResponse.text();
  let responseBody: unknown = responseText;

  try {
    responseBody = responseText ? JSON.parse(responseText) : {};
  } catch {
    responseBody = { error: responseText };
  }

  if (!upstreamResponse.ok) {
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

  const parsed = responseBody as OpenAIChatResponse;
  const message = parsed.choices?.[0]?.message?.content;

  return NextResponse.json({
    message:
      typeof message === "string" && message.trim()
        ? message
        : "I received the turn, but the model returned an empty response.",
    sessionId: body.sessionId,
  });
}
