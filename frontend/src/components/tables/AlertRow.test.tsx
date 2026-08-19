import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { AlertRow } from "./AlertRow"
import type { AlertHistoryItem } from "@/api/types"

const BASE = "http://localhost:8000"

function baseAlert(overrides: Partial<AlertHistoryItem> = {}): AlertHistoryItem {
  return {
    id: "alert-1",
    prediction_id: "pred-1",
    created_at: "2026-01-01T00:00:00Z",
    level: "high",
    title: "DoS attack detected",
    message: "Elevated risk score from repeated SYN floods.",
    risk_score: 82.3,
    attack_category: "dos",
    mitre: { tactic: "Impact", techniques: [{ id: "T1498", name: "Network DoS", url: "https://x" }] },
    acknowledged: false,
    source: "agent",
    ...overrides,
  }
}

function renderRow(alert: AlertHistoryItem) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <table>
        <tbody>
          <AlertRow alert={alert} />
        </tbody>
      </table>
    </QueryClientProvider>
  )
}

describe("AlertRow", () => {
  it("renders collapsed by default, with no detail panel", () => {
    renderRow(baseAlert())

    expect(screen.getByText("DoS attack detected")).toBeInTheDocument()
    expect(screen.queryByText("Threat Intelligence")).not.toBeInTheDocument()
  })

  it("expands to show Detection/MITRE/Threat Intelligence on click", async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () =>
        HttpResponse.json({ items: [] })
      )
    )
    renderRow(baseAlert())

    await user.click(screen.getByRole("button", { expanded: false }))

    expect(screen.getByText("Detection")).toBeInTheDocument()
    expect(screen.getByText("MITRE ATT&CK")).toBeInTheDocument()
    expect(screen.getByText("Threat Intelligence")).toBeInTheDocument()
  })

  it("shows an ML source badge for a non-rule alert", async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () =>
        HttpResponse.json({ items: [] })
      )
    )
    renderRow(baseAlert({ source: "agent" }))

    await user.click(screen.getByRole("button", { expanded: false }))

    expect(screen.getByTitle("Raised by the ML classifier")).toHaveTextContent("ML")
  })

  it("shows a Signature source badge for a rule-sourced alert", async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () =>
        HttpResponse.json({ items: [] })
      )
    )
    renderRow(baseAlert({ source: "rule" }))

    await user.click(screen.getByRole("button", { expanded: false }))

    expect(screen.getByTitle("Raised by a signature/rule match")).toHaveTextContent("Signature")
  })

  it("shows 'no network indicators' when the alert has none", async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () =>
        HttpResponse.json({ items: [] })
      )
    )
    renderRow(baseAlert())

    await user.click(screen.getByRole("button", { expanded: false }))

    await waitFor(() =>
      expect(screen.getByText("No network indicators available for this detection.")).toBeInTheDocument()
    )
  })

  it("renders provider verdict pills once enrichment resolves", async () => {
    const user = userEvent.setup()
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () =>
        HttpResponse.json({
          items: [
            {
              indicator: "8.8.8.8",
              indicator_role: "dst",
              provider: "abuseipdb",
              verdict: "malicious",
              confidence: 90,
              raw_response: {},
              looked_up_at: "2026-01-01T00:00:00Z",
              expires_at: "2026-01-02T00:00:00Z",
            },
          ],
        })
      )
    )
    renderRow(baseAlert())

    await user.click(screen.getByRole("button", { expanded: false }))

    await waitFor(() => expect(screen.getByText("8.8.8.8")).toBeInTheDocument())
    const tiSection = screen.getByText("8.8.8.8").closest("div")!
    expect(within(tiSection.parentElement!).getByText("abuseipdb: Malicious")).toBeInTheDocument()
  })

  it("does not poll enrichment while collapsed", () => {
    let requestCount = 0
    server.use(
      http.get(`${BASE}/history/alerts/alert-1/enrichment`, () => {
        requestCount += 1
        return HttpResponse.json({ items: [] })
      })
    )
    renderRow(baseAlert())

    expect(requestCount).toBe(0)
  })
})
