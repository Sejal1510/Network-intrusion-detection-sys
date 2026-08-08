import { render, screen, waitFor } from "@testing-library/react"
import { MemoryRouter, Route, Routes } from "react-router-dom"
import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { UserAuthProvider } from "@/context/UserAuthProvider"
import { RequireAuth } from "./RequireAuth"

const BASE = "http://localhost:8000"

function renderAt(path: string) {
  // Mirrors App.tsx's real nesting: an outer login-only gate around "/"
  // and "/devices", plus an inner role="admin" gate around "/devices" --
  // a role-mismatch redirect must land on a route the user *can* see, so
  // it targets "/", not the /devices route it was rejected from.
  return render(
    <MemoryRouter initialEntries={[path]}>
      <UserAuthProvider>
        <Routes>
          <Route path="/login" element={<div>Login page</div>} />
          <Route element={<RequireAuth />}>
            <Route path="/" element={<div>Protected content</div>} />
            <Route element={<RequireAuth role="admin" />}>
              <Route path="/devices" element={<div>Admin-only content</div>} />
            </Route>
          </Route>
        </Routes>
      </UserAuthProvider>
    </MemoryRouter>
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
})
