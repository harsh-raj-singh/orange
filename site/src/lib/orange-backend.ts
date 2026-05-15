type BackendFetchOptions = {
  method?: string;
  body?: unknown;
  signal?: AbortSignal;
};

export function getOrangeBackendUrl() {
  return process.env.ORANGE_BACKEND_URL?.replace(/\/+$/, "") || "";
}

export async function orangeBackendFetch<T>(path: string, options: BackendFetchOptions = {}) {
  const baseUrl = getOrangeBackendUrl();
  if (!baseUrl) {
    return null;
  }

  const response = await fetch(`${baseUrl}${path}`, {
    method: options.method ?? "GET",
    signal: options.signal,
    headers: options.body ? { "Content-Type": "application/json" } : undefined,
    body: options.body ? JSON.stringify(options.body) : undefined,
    cache: "no-store",
  });

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
