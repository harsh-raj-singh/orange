import { NextResponse } from "next/server";

import type { CompleteDemoConversationInput } from "@/lib/demo-memory-graph";
import { orangeBackendFetch } from "@/lib/orange-backend";

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

  try {
    const backendResult = await orangeBackendFetch<Record<string, unknown>>("/demo/complete", {
      method: "POST",
      body: completionBody,
    });

    if (!backendResult) {
      return NextResponse.json(
        {
          error: "Orange backend is not configured; completion was not persisted.",
          persisted: false,
        },
        { status: 503 },
      );
    }

    return NextResponse.json({
      ...backendResult,
      persisted: true,
      source: "backend",
    });
  } catch (error) {
    return NextResponse.json(
      {
        error: error instanceof Error ? error.message : "Orange backend completion failed.",
        persisted: false,
      },
      { status: 503 },
    );
  }
}
