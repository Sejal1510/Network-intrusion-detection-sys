import { act, renderHook, waitFor } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { useUserAuth } from "./useUserAuth"

const BASE = "http://localhost:8000"

describe("useUserAuth", () => {
  it("starts anonymous with no stored token", () => {
    const { result } = renderHook(() => useUserAuth())

    expect(result.current.status).toBe("anonymous")
    expect(result.current.user).toBeNull()
    expect(result.current.token).toBeNull()
  })

  it("login succeeds and persists token + user", async () => {
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ token: "sess-1", username: "analyst1", role: "analyst" })
      )
    )
    const { result } = renderHook(() => useUserAuth())

    await act(async () => {
      await result.current.login("analyst1", "hunter2")
    })

    expect(result.current.status).toBe("authenticated")
    expect(result.current.user).toEqual({ username: "analyst1", role: "analyst" })
    expect(result.current.token).toBe("sess-1")
    expect(window.localStorage.getItem("nids_session_token")).toBe("sess-1")
  })

  it("login fails with 401 sets error and stays anonymous", async () => {
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ detail: "Invalid username or password." }, { status: 401 })
      )
    )
    const { result } = renderHook(() => useUserAuth())

    await act(async () => {
      await expect(result.current.login("analyst1", "wrong")).rejects.toThrow()
    })

    expect(result.current.status).toBe("anonymous")
    expect(result.current.user).toBeNull()
    expect(result.current.error).toMatch(/invalid username or password/i)
  })

  it("logout clears token and user, calls POST /auth/logout", async () => {
    let logoutCalled = false
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ token: "sess-1", username: "analyst1", role: "analyst" })
      ),
      http.post(`${BASE}/auth/logout`, () => {
        logoutCalled = true
        return new HttpResponse(null, { status: 204 })
      })
    )
    const { result } = renderHook(() => useUserAuth())
    await act(async () => {
      await result.current.login("analyst1", "hunter2")
    })

    await act(async () => {
      await result.current.logout()
    })

    expect(logoutCalled).toBe(true)
    expect(result.current.status).toBe("anonymous")
    expect(result.current.user).toBeNull()
    expect(result.current.token).toBeNull()
    expect(window.localStorage.getItem("nids_session_token")).toBeNull()
  })

  it("rehydrates from a stored token via GET /auth/me on mount", async () => {
    window.localStorage.setItem("nids_session_token", "existing-token")
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json({ username: "admin1", role: "admin" })
      )
    )

    const { result } = renderHook(() => useUserAuth())

    expect(result.current.status).toBe("loading")
    await waitFor(() => expect(result.current.status).toBe("authenticated"))
    expect(result.current.user).toEqual({ username: "admin1", role: "admin" })
    expect(result.current.token).toBe("existing-token")
  })

  it("clears a stale/expired stored token when /auth/me 401s", async () => {
    window.localStorage.setItem("nids_session_token", "stale-token")
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json({ detail: "Not authenticated." }, { status: 401 })
      )
    )

    const { result } = renderHook(() => useUserAuth())

    await waitFor(() => expect(result.current.status).toBe("anonymous"))
    expect(result.current.token).toBeNull()
    expect(window.localStorage.getItem("nids_session_token")).toBeNull()
  })
})
