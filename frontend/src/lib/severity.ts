import type { Severity } from "@/api/types"

export interface SeverityMeta {
  label: string
  /** CSS custom property name (see index.css), e.g. "--status-good". */
  colorVar: string
  icon: "check" | "warning" | "alert"
}

const SEVERITY_META: Record<Severity, SeverityMeta> = {
  low: { label: "Low", colorVar: "--status-good", icon: "check" },
  medium: { label: "Medium", colorVar: "--status-warning", icon: "warning" },
  high: { label: "High", colorVar: "--status-serious", icon: "warning" },
  critical: { label: "Critical", colorVar: "--status-critical", icon: "alert" },
}

const SEVERITY_ORDER: Severity[] = ["low", "medium", "high", "critical"]

export function severityMeta(severity: Severity): SeverityMeta {
  return SEVERITY_META[severity]
}

export function severityRank(severity: Severity): number {
  return SEVERITY_ORDER.indexOf(severity)
}

export function compareSeverityDesc(a: Severity, b: Severity): number {
  return severityRank(b) - severityRank(a)
}
