import { NextResponse } from "next/server";

import {
  completeDemoConversation,
  type CompleteDemoConversationInput,
} from "@/lib/demo-memory-store";

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

  const graph = completeDemoConversation(body);

  return NextResponse.json(graph);
}
