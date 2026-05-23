type BackendFetchOptions = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
  cache?: RequestCache;
  next?: {
    revalidate?: number | false;
    tags?: string[];
  };
};

const DEFAULT_LOCAL_BACKEND_URL = "http://127.0.0.1:8001";

export function getOrangeBackendUrl() {
  const configuredUrl =
    process.env.ORANGE_BACKEND_URL?.trim() ||
    process.env.NEXT_PUBLIC_ORANGE_BACKEND_URL?.trim() ||
    "";

  if (configuredUrl) {
    return configuredUrl.replace(/\/+$/, "");
  }

  return process.env.NODE_ENV === "production" ? "" : DEFAULT_LOCAL_BACKEND_URL;
}

export async function orangeBackendFetch<T>(path: string, options: BackendFetchOptions = {}) {
  const baseUrl = getOrangeBackendUrl();
  if (!baseUrl) {
    return null;
  }

  const requestInit: RequestInit & { next?: BackendFetchOptions["next"] } = {
    method: options.method ?? "GET",
    signal: options.signal,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
  };
  if (options.cache) {
    requestInit.cache = options.cache;
  } else if (!options.next) {
    requestInit.cache = "no-store";
  }
  if (options.next) {
    requestInit.next = options.next;
  }

  const response = await fetch(`${baseUrl}${path}`, requestInit);

  const text = await response.text();
  const data = text ? (JSON.parse(text) as T) : ({} as T);

  if (!response.ok) {
    const message =
      data && typeof data === "object" && "error" in data && typeof data.error === "string"
        ? data.error
        : `Orange backend returned ${response.status}.`;
    throw new Error(message);
  }

  return data;
}
