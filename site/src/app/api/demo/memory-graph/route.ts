import { NextResponse } from "next/server";

import { getDemoMemoryGraphSnapshot } from "@/lib/demo-memory-store";

export const dynamic = "force-dynamic";

export function GET() {
  return NextResponse.json(getDemoMemoryGraphSnapshot());
}
