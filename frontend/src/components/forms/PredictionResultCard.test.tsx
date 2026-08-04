import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { PredictionResultCard } from "./PredictionResultCard"
import type { PredictResponse } from "@/api/types"

function makeResponse(overrides: Partial<PredictResponse> = {}): PredictResponse {
  return {
    prediction: "dos",
    probabilities: { normal: 0.05, dos: 0.95 },
    confidence: 0.95,
    attack_category: "dos",
    anomaly_score: null,
    is_anomaly: null,
    severity: "critical",
    explanation: null,
    risk_score: { score: 91.2, severity: "critical", factors: { attack_confidence: 0.475 } },
    mitre: { tactic: "Impact", techniques: [{ id: "T1498", name: "Network DoS", url: "https://x" }] },
    alert_id: null,
    ...overrides,
  }
}

describe("PredictionResultCard", () => {
  it("renders a full response without throwing", () => {
    render(<PredictionResultCard result={makeResponse()} />)

    expect(screen.getByText("Dos")).toBeInTheDocument()
    expect(screen.getByText("91.2 / 100")).toBeInTheDocument()
    expect(screen.getByText("T1498")).toBeInTheDocument()
  })

  it("shows the alert banner when alert_id is present", () => {
    render(<PredictionResultCard result={makeResponse({ alert_id: "alert-123" })} />)

    expect(screen.getByText(/raised an alert/i)).toBeInTheDocument()
  })

  it("omits the alert banner when alert_id is null", () => {
    render(<PredictionResultCard result={makeResponse({ alert_id: null })} />)

    expect(screen.queryByText(/raised an alert/i)).not.toBeInTheDocument()
  })
})
