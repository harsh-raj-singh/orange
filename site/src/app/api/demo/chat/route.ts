import { NextResponse } from "next/server";

const NVIDIA_CHAT_COMPLETIONS_URL =
  "https://integrate.api.nvidia.com/v1/chat/completions";
const DEFAULT_NVIDIA_MODEL = "deepseek-ai/deepseek-v4-pro";
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

type NvidiaChatResponse = {
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

export const dynamic = "force-dynamic";

export async function POST(request: Request) {
  const apiKey = process.env.NVIDIA_API_KEY;

  if (!apiKey) {
    return NextResponse.json(
      { error: "NVIDIA_API_KEY is not configured on the server." },
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

  const timeoutMs = Number(process.env.NVIDIA_CHAT_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);
  let upstreamResponse: Response;

  try {
    upstreamResponse = await fetch(NVIDIA_CHAT_COMPLETIONS_URL, {
      method: "POST",
      signal: controller.signal,
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        model: process.env.NVIDIA_CHAT_MODEL ?? body.model ?? DEFAULT_NVIDIA_MODEL,
        messages: [
          {
            role: "system",
            content: createSystemPrompt(body.profile),
          },
          ...messages,
        ],
        temperature: body.temperature ?? 0.7,
        top_p: 0.95,
        max_tokens: body.max_tokens ?? 512,
        chat_template_kwargs: { thinking: false },
        stream: false,
      }),
    });
  } catch (error) {
    const isAbort =
      error instanceof Error &&
      (error.name === "AbortError" || error.message.toLowerCase().includes("aborted"));

    return NextResponse.json(
      {
        error: isAbort
          ? "NVIDIA chat timed out. The API key is valid, but the chat completion endpoint did not respond quickly enough."
          : "NVIDIA chat request failed before a response was returned.",
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
          typeof (responseBody as NvidiaChatResponse).error?.message === "string"
            ? (responseBody as NvidiaChatResponse).error?.message
            : "NVIDIA chat request failed.",
      },
      { status: upstreamResponse.status },
    );
  }

  const parsed = responseBody as NvidiaChatResponse;
  const message = parsed.choices?.[0]?.message?.content;

  return NextResponse.json({
    message:
      typeof message === "string" && message.trim()
        ? message
        : "I received the turn, but the model returned an empty response.",
    sessionId: body.sessionId,
  });
}
