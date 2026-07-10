import { NextResponse } from "next/server";

import { orangeBackendFetch } from "@/lib/orange-backend";
import { normalizeDemoGraphScope } from "@/lib/api";
import { getVerifiedSupabaseSession } from "@/lib/supabase-server";

export const dynamic = "force-dynamic";

const NO_STORE_HEADERS = {
  "Cache-Control": "no-store, max-age=0",
  "CDN-Cache-Control": "no-store",
  "Vercel-CDN-Cache-Control": "no-store",
};

type BackendGraphVersion = {
  version?: unknown;
  node_count?: unknown;
  nodeCount?: unknown;
  last_changed_at?: unknown;
  lastChangedAt?: unknown;
};

function normalizedVersion(value: unknown) {
  if (typeof value === "string" && value.trim()) {
    return value;
  }
  return typeof value === "number" && Number.isFinite(value) ? String(value) : null;
}

function normalizedCount(value: unknown) {
  if (typeof value === "number" && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }
  return 0;
}

export async function GET(request: Request) {
  const params = new URL(request.url).searchParams;
  const scope = normalizeDemoGraphScope(params.get("scope"));
  const company = params.get("company")?.trim();
  const auth = await getVerifiedSupabaseSession();

  if (!auth) {
    return NextResponse.json(
      { version: "preview", nodeCount: 0, lastChangedAt: null, source: "fallback" },
      { headers: NO_STORE_HEADERS },
    );
  }

  const backendParams = new URLSearchParams({ scope });
  backendParams.set("user_email", auth.email);
  backendParams.set("user_id", auth.userId);
  if (company) {
    backendParams.set("company", company);
    backendParams.set("org_id", company.toLowerCase());
  }

  try {
    const result = await orangeBackendFetch<BackendGraphVersion>(
      `/graph/version?${backendParams.toString()}`,
      {
        cache: "no-store",
        headers: { Authorization: `Bearer ${auth.accessToken}` },
      },
    );
    const version = normalizedVersion(result?.version);
    if (!result || !version) {
      throw new Error("Orange backend did not return a graph version.");
    }

    return NextResponse.json(
      {
        version,
        nodeCount: normalizedCount(result.node_count ?? result.nodeCount),
        lastChangedAt:
          typeof (result.last_changed_at ?? result.lastChangedAt) === "string"
            ? (result.last_changed_at ?? result.lastChangedAt)
            : null,
        source: "backend",
      },
      { headers: NO_STORE_HEADERS },
    );
  } catch (error) {
    console.warn("orange_backend_graph_version_failed", error);
    return NextResponse.json(
      { version: "unavailable", nodeCount: 0, lastChangedAt: null, source: "fallback" },
      { headers: NO_STORE_HEADERS },
    );
  }
}
