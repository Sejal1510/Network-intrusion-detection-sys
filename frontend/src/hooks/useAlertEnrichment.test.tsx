import { renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { useAlertEnrichment } from "./useAlertEnrichment"
import type { ReactNode } from "react"

const BASE = "http://localhost:8000"

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
}

afterEach(() => {
  vi.useRealTimers()
})

describe("useAlertEnrichment", () => {
  it("does not fetch at all when disabled (row collapsed)", () => {
    let requestCount = 0
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () => {
        requestCount += 1
        return HttpResponse.json({ items: [] })
      })
    )

    renderHook(() => useAlertEnrichment("alert-1", false), { wrapper })

    expect(requestCount).toBe(0)
  })

  it("stops polling as soon as a non-empty result lands", async () => {
    let requestCount = 0
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () => {
        requestCount += 1
        const items =
          requestCount >= 2
            ? [
                {
                  indicator: "8.8.8.8",
                  indicator_role: "dst",
                  provider: "abuseipdb",
                  verdict: "benign",
                  confidence: 5,
                  raw_response: {},
                  looked_up_at: "2026-01-01T00:00:00Z",
                  expires_at: "2026-01-02T00:00:00Z",
                },
              ]
            : []
        return HttpResponse.json({ items })
      })
    )

    const { result } = renderHook(() => useAlertEnrichment("alert-1", true), { wrapper })

    await waitFor(() => expect(result.current.data?.items).toHaveLength(1), { timeout: 5000 })
    const countAfterResolved = requestCount

    // Give it a moment -- if polling didn't actually stop, this would tick again.
    await new Promise((resolve) => setTimeout(resolve, 300))
    expect(requestCount).toBe(countAfterResolved)
  })
})
