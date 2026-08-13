import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { MemoryRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { DevicesPage } from "./DevicesPage"
import type { DeviceListItem } from "@/api/types"

const BASE = "http://localhost:8000"

const DEVICE: DeviceListItem = {
  id: "dev-1",
  name: "sensor-1",
  user_id: null,
  paired_at: "2026-08-01T00:00:00Z",
  last_seen_at: null,
  revoked: false,
}

function renderPage() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <DevicesPage />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe("DevicesPage", () => {
  it("asks for confirmation before revoking, and does not call the API on cancel", async () => {
    const user = userEvent.setup()
    let revokeCalled = false
    server.use(
      http.get(`${BASE}/devices`, () =>
        HttpResponse.json({ items: [DEVICE], total: 1, limit: 20, offset: 0 })
      ),
      http.post(`${BASE}/devices/:id/revoke`, () => {
        revokeCalled = true
        return HttpResponse.json({ ...DEVICE, revoked: true })
      })
    )
    renderPage()

    await user.click(await screen.findByRole("button", { name: /revoke/i }))
    const dialog = await screen.findByRole("alertdialog")

    await user.click(within(dialog).getByRole("button", { name: /cancel/i }))

    expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument()
    expect(revokeCalled).toBe(false)
  })

  it("revokes the device only after the dialog is confirmed", async () => {
    const user = userEvent.setup()
    let revokeCalled = false
    server.use(
      http.get(`${BASE}/devices`, () =>
        HttpResponse.json({ items: [DEVICE], total: 1, limit: 20, offset: 0 })
      ),
      http.post(`${BASE}/devices/:id/revoke`, () => {
        revokeCalled = true
        return HttpResponse.json({ ...DEVICE, revoked: true })
      })
    )
    renderPage()

    await user.click(await screen.findByRole("button", { name: /revoke/i }))
    const dialog = await screen.findByRole("alertdialog")
    expect(revokeCalled).toBe(false)

    await user.click(within(dialog).getByRole("button", { name: /revoke/i }))

    await waitFor(() => expect(revokeCalled).toBe(true))
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument())
  })
})
