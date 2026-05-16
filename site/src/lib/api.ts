import { orangeBackendFetch } from "@/lib/orange-backend";

export type DemoGraphScope = "user" | "global" | "both";
export type MemoryScope = "user" | "global";

type BackendFallbackOptions<TBackend, TResult> = {
  path: string;
  request?: {
    method?: string;
    body?: unknown;
    signal?: AbortSignal;
  };
  warning: string;
  transform: (data: TBackend) => TResult | null | Promise<TResult | null>;
  fallback: () => TResult;
};

export type FallbackResponse<T> = T & {
  source?: "backend" | "fallback";
};

export function normalizeDemoGraphScope(value: string | null): DemoGraphScope {
  return value === "user" || value === "global" || value === "both" ? value : "both";
}

export function normalizeMemoryScope(value: unknown): MemoryScope {
  return value === "global" || value === "shared" ? "global" : "user";
}

export async function backendJsonOrFallback<TBackend, TResult>({
  path,
  request,
  warning,
  transform,
  fallback,
}: BackendFallbackOptions<TBackend, TResult>) {
  try {
    const backendResult = await orangeBackendFetch<TBackend>(path, request);
    if (backendResult) {
      const transformed = await transform(backendResult);
      if (transformed) {
        return { ...transformed, source: "backend" };
      }
    }
  } catch (error) {
    console.warn(warning, error);
  }

  console.warn(`${warning}_serving_fallback`);
  return { ...fallback(), source: "fallback" };
}
