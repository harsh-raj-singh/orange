import { NextResponse } from "next/server";

import { getDemoMemoryGraph } from "@/lib/demo-memory-graph";

export const dynamic = "force-static";

export function GET() {
  return NextResponse.json(getDemoMemoryGraph());
}
