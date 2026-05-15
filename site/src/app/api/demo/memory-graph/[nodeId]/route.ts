import { NextResponse } from "next/server";

import { getDemoMemoryNodeDetailFromStore } from "@/lib/demo-memory-store";

export const dynamic = "force-dynamic";

type RouteContext = {
  params: Promise<{
    nodeId: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { nodeId } = await context.params;
  const node = getDemoMemoryNodeDetailFromStore(nodeId);

  if (!node) {
    return NextResponse.json(
      {
        error: "Demo memory node not found",
      },
      { status: 404 },
    );
  }

  return NextResponse.json(node);
}
