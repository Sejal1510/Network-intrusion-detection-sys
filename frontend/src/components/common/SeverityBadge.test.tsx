import { render, screen } from "@testing-library/react"
import { describe, expect, it } from "vitest"
import { SeverityBadge } from "./SeverityBadge"
import type { Severity } from "@/api/types"

describe("SeverityBadge", () => {
  it.each<[Severity, string]>([
    ["low", "Low"],
    ["medium", "Medium"],
    ["high", "High"],
    ["critical", "Critical"],
  ])("renders an icon and the %s label", (severity, label) => {
    render(<SeverityBadge severity={severity} />)

    expect(screen.getByText(label)).toBeInTheDocument()
    // icon+label, never color alone -- the badge must ship an svg icon too
    const badge = screen.getByText(label).closest("span")
    expect(badge?.querySelector("svg")).not.toBeNull()
  })
})
