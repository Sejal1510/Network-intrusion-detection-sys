import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { apiClient } from "@/api/client"
import { useUserAuth } from "./useUserAuth"

const BASE = "http://localhost:8000"

// useUserAuth calls useQueryClient() (to clear the cache on any session
// teardown -- see clearLocalSession), so every render needs a real
// QueryClientProvider ancestor, not just msw/localStorage mocking.
function renderUseUserAuth() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return renderHook(() => useUserAuth(), {
    wrapper: ({ children }) => <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>,
  })
}

describe("useUserAuth", () => {
  it("starts anonymous with no stored token", () => {
    const { result } = renderUseUserAuth()

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
    const { result } = renderUseUserAuth()

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
    const { result } = renderUseUserAuth()

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
    const { result } = renderUseUserAuth()
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

    const { result } = renderUseUserAuth()

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

    const { result } = renderUseUserAuth()

    await waitFor(() => expect(result.current.status).toBe("anonymous"))
    expect(result.current.token).toBeNull()
    expect(window.localStorage.getItem("nids_session_token")).toBeNull()
  })

  it("clears the session when a request made mid-session (after a valid login) comes back 401", async () => {
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ token: "sess-1", username: "analyst1", role: "analyst" })
      )
    )
    const { result } = renderUseUserAuth()
    await act(async () => {
      await result.current.login("analyst1", "hunter2")
    })
    expect(result.current.status).toBe("authenticated")

    // Any other authenticated endpoint expiring mid-session -- not a
    // second /auth/me call, to prove this isn't special-cased to
    // rehydration.
    server.use(
      http.get(`${BASE}/history/alerts`, () =>
        HttpResponse.json({ detail: "Session expired." }, { status: 401 })
      )
    )
    await act(async () => {
      await expect(apiClient.get("/history/alerts")).rejects.toThrow()
    })

    await waitFor(() => expect(result.current.status).toBe("anonymous"))
    expect(result.current.user).toBeNull()
    expect(result.current.token).toBeNull()
    expect(window.localStorage.getItem("nids_session_token")).toBeNull()
  })

  it("does not force a logout for a 403 (still a valid session, just an unauthorized role)", async () => {
    server.use(
      http.post(`${BASE}/auth/login`, () =>
        HttpResponse.json({ token: "sess-1", username: "analyst1", role: "analyst" })
      )
    )
    const { result } = renderUseUserAuth()
    await act(async () => {
      await result.current.login("analyst1", "hunter2")
    })

    server.use(
      http.get(`${BASE}/devices`, () =>
        HttpResponse.json({ detail: "Admin role required." }, { status: 403 })
      )
    )
    await act(async () => {
      await expect(apiClient.get("/devices")).rejects.toThrow()
    })

    expect(result.current.status).toBe("authenticated")
    expect(result.current.token).toBe("sess-1")
  })
})
