import { NextResponse } from "next/server";

import { getDemoMemoryNodeDetail } from "@/lib/demo-memory-graph";

export const dynamic = "force-static";

type RouteContext = {
  params: Promise<{
    nodeId: string;
  }>;
};

export async function GET(_request: Request, context: RouteContext) {
  const { nodeId } = await context.params;
  const node = getDemoMemoryNodeDetail(nodeId);

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
