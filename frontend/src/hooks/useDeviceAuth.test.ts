import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { useDeviceAuth } from "./useDeviceAuth"

const BASE = "http://localhost:8000"

describe("useDeviceAuth", () => {
  it("starts unpaired with no stored token", () => {
    const { result } = renderHook(() => useDeviceAuth())

    expect(result.current.status).toBe("unpaired")
    expect(result.current.token).toBeNull()
  })

  it("pairs, exchanges, and persists the token on ensurePaired()", async () => {
    server.use(
      http.post(`${BASE}/agent/pair`, () =>
        HttpResponse.json({ pairing_token: "ptok", expires_in_seconds: 600 })
      ),
      http.post(`${BASE}/agent/pair/exchange`, () =>
        HttpResponse.json({ device_id: "dev-1", token: "device-token-1" })
      )
    )
    const { result } = renderHook(() => useDeviceAuth())

    let resolved: string | undefined
    await act(async () => {
      resolved = await result.current.ensurePaired()
    })

    expect(resolved).toBe("device-token-1")
    await waitFor(() => expect(result.current.status).toBe("ready"))
    expect(result.current.token).toBe("device-token-1")
    expect(window.localStorage.getItem("nids_device_token")).toBe("device-token-1")
  })

  it("skips pairing when a token is already stored", async () => {
    window.localStorage.setItem("nids_device_token", "existing-token")
    let pairCalled = false
    server.use(
      http.post(`${BASE}/agent/pair`, () => {
        pairCalled = true
        return HttpResponse.json({ pairing_token: "ptok", expires_in_seconds: 600 })
      })
    )
    const { result } = renderHook(() => useDeviceAuth())

    expect(result.current.status).toBe("ready")

    let resolved: string | undefined
    await act(async () => {
      resolved = await result.current.ensurePaired()
    })

    expect(resolved).toBe("existing-token")
    expect(pairCalled).toBe(false)
  })

  it("moves to unavailable when exchange 503s (no database configured)", async () => {
    server.use(
      http.post(`${BASE}/agent/pair`, () =>
        HttpResponse.json({ pairing_token: "ptok", expires_in_seconds: 600 })
      ),
      http.post(
        `${BASE}/agent/pair/exchange`,
        () => HttpResponse.json({ detail: "No database is configured." }, { status: 503 })
      )
    )
    const { result } = renderHook(() => useDeviceAuth())

    await act(async () => {
      await expect(result.current.ensurePaired()).rejects.toThrow()
    })

    await waitFor(() => expect(result.current.status).toBe("unavailable"))
    expect(result.current.token).toBeNull()
    expect(result.current.error).toMatch(/database/i)
  })
})
