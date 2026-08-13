import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { UserAuthProvider } from "@/context/UserAuthProvider"
import { apiClient } from "@/api/client"
import { RequireAuth } from "./RequireAuth"

const BASE = "http://localhost:8000"

/** Stand-in for any page that makes an authenticated request after mount. */
function ProtectedContent() {
  return (
    <div>
      Protected content
      <button onClick={() => void apiClient.get("/history/alerts").catch(() => {})}>
        Trigger request
      </button>
    </div>
  )
}

function renderAt(path: string) {
  // Mirrors App.tsx's real nesting: an outer login-only gate around "/"
  // and "/devices", plus an inner role="admin" gate around "/devices" --
  // a role-mismatch redirect must land on a route the user *can* see, so
  // it targets "/", not the /devices route it was rejected from.
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[path]}>
        <UserAuthProvider>
          <Routes>
            <Route path="/login" element={<div>Login page</div>} />
            <Route element={<RequireAuth />}>
              <Route path="/" element={<ProtectedContent />} />
              <Route element={<RequireAuth role="admin" />}>
                <Route path="/devices" element={<div>Admin-only content</div>} />
              </Route>
            </Route>
          </Routes>
        </UserAuthProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("RequireAuth", () => {
  it("redirects an anonymous user to /login", async () => {
    renderAt("/")

    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument())
  })

  it("renders protected content for an authenticated user", async () => {
    window.localStorage.setItem("nids_session_token", "valid-token")
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json({ username: "analyst1", role: "analyst" })
      )
    )

    renderAt("/")

    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument())
  })

  it("redirects a non-admin away from an admin-only route", async () => {
    window.localStorage.setItem("nids_session_token", "valid-token")
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json({ username: "analyst1", role: "analyst" })
      )
    )

    renderAt("/devices")

    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument())
  })

  it("renders admin-only content for an admin user", async () => {
    window.localStorage.setItem("nids_session_token", "valid-token")
    server.use(
      http.get(`${BASE}/auth/me`, () => HttpResponse.json({ username: "root", role: "admin" }))
    )

    renderAt("/devices")

    await waitFor(() => expect(screen.getByText("Admin-only content")).toBeInTheDocument())
  })

  it("redirects to /login when a request expires the session mid-use", async () => {
    const user = userEvent.setup()
    window.localStorage.setItem("nids_session_token", "valid-token")
    server.use(
      http.get(`${BASE}/auth/me`, () =>
        HttpResponse.json({ username: "analyst1", role: "analyst" })
      )
    )

    renderAt("/")
    await waitFor(() => expect(screen.getByText("Protected content")).toBeInTheDocument())

    server.use(
      http.get(`${BASE}/history/alerts`, () =>
        HttpResponse.json({ detail: "Session expired." }, { status: 401 })
      )
    )
    await user.click(screen.getByRole("button", { name: "Trigger request" }))

    await waitFor(() => expect(screen.getByText("Login page")).toBeInTheDocument())
    expect(window.localStorage.getItem("nids_session_token")).toBeNull()
  })
})
