import { describe, expect, it } from "vitest"
import { compareSeverityDesc, severityMeta, severityRank } from "./severity"
import type { Severity } from "@/api/types"

describe("severityMeta", () => {
  const cases: [Severity, string, string][] = [
    ["low", "Low", "--status-good"],
    ["medium", "Medium", "--status-warning"],
    ["high", "High", "--status-serious"],
    ["critical", "Critical", "--status-critical"],
  ]

  it.each(cases)("maps %s to label %s and color %s", (severity, label, colorVar) => {
    const meta = severityMeta(severity)
    expect(meta.label).toBe(label)
    expect(meta.colorVar).toBe(colorVar)
  })
})

describe("severityRank / compareSeverityDesc", () => {
  it("orders low < medium < high < critical", () => {
    expect(severityRank("low")).toBeLessThan(severityRank("medium"))
    expect(severityRank("medium")).toBeLessThan(severityRank("high"))
    expect(severityRank("high")).toBeLessThan(severityRank("critical"))
  })

  it("sorts a mixed list critical-first", () => {
    const sorted = (["low", "critical", "medium", "high"] as Severity[]).sort(compareSeverityDesc)
    expect(sorted).toEqual(["critical", "high", "medium", "low"])
  })
})
