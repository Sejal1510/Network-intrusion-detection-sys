import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { useLiveFeed } from "./useLiveFeed"
import type { PredictResponse } from "@/api/types"

const BASE = "http://localhost:8000"

class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  url: string
  onopen: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  onclose: (() => void) | null = null
  onerror: (() => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    FakeWebSocket.instances.push(this)
  }

  close() {
    if (this.closed) return
    this.closed = true
    this.onclose?.()
  }

  send() {}
}

function makeResponse(overrides: Partial<PredictResponse> = {}): PredictResponse {
  return {
    prediction: "dos",
    probabilities: null,
    confidence: 0.9,
    attack_category: "dos",
    anomaly_score: null,
    is_anomaly: null,
    severity: "high",
    explanation: null,
    risk_score: { score: 80, severity: "high", factors: { attack_confidence: 0.5 } },
    mitre: null,
    alert_id: null,
    ...overrides,
  }
}

beforeEach(() => {
  FakeWebSocket.instances = []
  vi.stubGlobal("WebSocket", FakeWebSocket)
  server.use(
    http.post(`${BASE}/auth/ws-ticket`, () =>
      HttpResponse.json({ ticket: "test-ticket", expires_in_seconds: 60 })
    ),
    http.get(`${BASE}/history/predictions`, () =>
      HttpResponse.json({ items: [], total: 0, limit: 100, offset: 0 })
    )
  )
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.useRealTimers()
})

describe("useLiveFeed", () => {
  it("connects and moves to live on open", async () => {
    const { result } = renderHook(() => useLiveFeed())

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    expect(result.current.status).toBe("connecting")

    act(() => FakeWebSocket.instances[0].onopen?.())

    expect(result.current.status).toBe("live")
  })

  it("goes offline without ever opening a socket if minting a ws-ticket fails", async () => {
    server.use(http.post(`${BASE}/auth/ws-ticket`, () => HttpResponse.json({ detail: "Not authenticated." }, { status: 401 })))

    const { result } = renderHook(() => useLiveFeed())

    await waitFor(() => expect(result.current.status).toBe("offline"))
    expect(FakeWebSocket.instances).toHaveLength(0)
  })

  it("buffers incoming messages newest-first", async () => {
    const { result } = renderHook(() => useLiveFeed())
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const socket = FakeWebSocket.instances[0]
    act(() => socket.onopen?.())

    act(() => {
      socket.onmessage?.({ data: JSON.stringify({ type: "prediction", data: makeResponse({ prediction: "first" }) }) })
      socket.onmessage?.({ data: JSON.stringify({ type: "prediction", data: makeResponse({ prediction: "second" }) }) })
    })

    expect(result.current.entries).toHaveLength(2)
    expect(result.current.entries[0].prediction).toBe("second")
    expect(result.current.entries[1].prediction).toBe("first")
  })

  it("dedupes messages that share the same alert_id", async () => {
    const { result } = renderHook(() => useLiveFeed())
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const socket = FakeWebSocket.instances[0]
    act(() => socket.onopen?.())

    act(() => {
      const msg = { type: "prediction", data: makeResponse({ alert_id: "alert-1" }) }
      socket.onmessage?.({ data: JSON.stringify(msg) })
      socket.onmessage?.({ data: JSON.stringify(msg) })
    })

    expect(result.current.entries).toHaveLength(1)
  })

  it("caps the buffer at 500 entries, dropping the oldest", async () => {
    const { result } = renderHook(() => useLiveFeed())
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const socket = FakeWebSocket.instances[0]
    act(() => socket.onopen?.())

    act(() => {
      for (let i = 0; i < 505; i++) {
        const msg = { type: "prediction", data: makeResponse({ prediction: i }) }
        socket.onmessage?.({ data: JSON.stringify(msg) })
      }
    })

    expect(result.current.entries).toHaveLength(500)
    expect(result.current.entries[0].prediction).toBe(504)
  })

  it("reconnects with backoff after an unexpected close, and backfills history", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    server.use(
      http.get(`${BASE}/history/predictions`, () =>
        HttpResponse.json({
          items: [
            {
              id: "hist-1",
              created_at: new Date().toISOString(),
              run_id: "run-1",
              anomaly_run_id: null,
              label_column: "attack_category",
              prediction: "probe",
              probabilities: null,
              confidence: 0.7,
              attack_category: "probe",
              anomaly_score: null,
              is_anomaly: null,
              severity: "medium",
              risk_score: 40,
              risk_factors: {},
              mitre: null,
              raw_record: {},
              source: "agent",
              explanation: null,
            },
          ],
          total: 1,
          limit: 100,
          offset: 0,
        })
      )
    )

    const { result } = renderHook(() => useLiveFeed())
    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(1))
    const first = FakeWebSocket.instances[0]
    act(() => first.onopen?.())
    act(() => {
      const msg = { type: "prediction", data: makeResponse() }
      first.onmessage?.({ data: JSON.stringify(msg) })
    })
    expect(result.current.entries).toHaveLength(1)

    act(() => first.close())
    expect(result.current.status).toBe("reconnecting")

    await act(async () => {
      await vi.advanceTimersByTimeAsync(2000)
    })

    await waitFor(() => expect(FakeWebSocket.instances).toHaveLength(2))
    act(() => FakeWebSocket.instances[1].onopen?.())

    expect(result.current.status).toBe("live")
    await waitFor(() => expect(result.current.entries.some((e) => e.id === "hist-1")).toBe(true))
  })
})
