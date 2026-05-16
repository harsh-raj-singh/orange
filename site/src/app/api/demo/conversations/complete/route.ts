import { NextResponse } from "next/server";

import {
  completeDemoConversation,
  type CompleteDemoConversationInput,
} from "@/lib/demo-memory-store";
import { backendJsonOrFallback } from "@/lib/api";

export const dynamic = "force-dynamic";

async function readCompletionBody(request: Request) {
  const rawBody = await request.text();

  if (!rawBody) {
    return {};
  }

  try {
    return JSON.parse(rawBody) as CompleteDemoConversationInput;
  } catch {
    return null;
  }
}

export async function POST(request: Request) {
  const body = await readCompletionBody(request);

  if (!body) {
    return NextResponse.json(
      { error: "Completion payload must be valid JSON." },
      { status: 400 },
    );
  }

  const completionBody: CompleteDemoConversationInput = {
    ...body,
    contribute_to_global: body.contribute_to_global ?? true,
  };

  return NextResponse.json(
    await backendJsonOrFallback<Record<string, unknown>, Record<string, unknown>>({
      path: "/demo/complete",
      request: {
        method: "POST",
        body: completionBody,
      },
      warning: "orange_backend_completion_failed",
      transform: (backendResult) => ({
        ...backendResult,
        persisted: true,
        fallback: false,
      }),
      fallback: () => ({
        ...completeDemoConversation(completionBody),
        persisted: false,
        fallback: true,
      }),
    }),
  );
}
