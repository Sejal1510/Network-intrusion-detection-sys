const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000"

export class ApiError extends Error {
  status: number

  constructor(status: number, detail: string) {
    super(detail)
    this.name = "ApiError"
    this.status = status
  }
}

async function parseErrorDetail(response: Response): Promise<string> {
  try {
    const body = (await response.json()) as { detail?: unknown }
    if (typeof body.detail === "string") return body.detail
    return JSON.stringify(body.detail)
  } catch {
    return response.statusText || `HTTP ${response.status}`
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init?.body && !(init.body instanceof FormData)
        ? { "Content-Type": "application/json" }
        : {}),
      ...init?.headers,
    },
  })

  if (!response.ok) {
    throw new ApiError(response.status, await parseErrorDetail(response))
  }

  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const apiClient = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    }),
}

/** The base URL the app was configured with, for building the /ws/live URL. */
export function apiBaseUrl(): string {
  return API_BASE_URL
}

/** ws(s)://…same-host equivalent of apiBaseUrl(), for the native WebSocket API. */
export function apiWebSocketUrl(path: string): string {
  const url = new URL(path, API_BASE_URL)
  url.protocol = url.protocol === "https:" ? "wss:" : "ws:"
  return url.toString()
}
