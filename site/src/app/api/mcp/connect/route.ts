import { NextResponse } from "next/server";

import { orangeBackendFetch } from "@/lib/orange-backend";

export const dynamic = "force-dynamic";

type ConnectResponse = {
  email: string;
  name?: string | null;
  token: string;
  mcp_url: string;
  codex_config: string;
  codex_command: string;
  claude_command: string;
};

export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as { credential?: string } | null;
  const credential = body?.credential?.trim();

  if (!credential) {
    return NextResponse.json({ error: "Google sign-in credential is required." }, { status: 400 });
  }

  try {
    const data = await orangeBackendFetch<ConnectResponse>("/mcp/connect", {
      method: "POST",
      body: { credential },
    });
    if (!data) {
      return NextResponse.json(
        { error: "Orange backend is not configured. Set ORANGE_BACKEND_URL first." },
        { status: 503 },
      );
    }
    return NextResponse.json(data);
  } catch (error) {
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Failed to create MCP token." },
      { status: 500 },
    );
  }
}
