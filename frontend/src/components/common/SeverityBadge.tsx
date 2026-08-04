import type { Severity } from "@/api/types"
import { severityMeta } from "@/lib/severity"

function Icon({ icon }: { icon: "check" | "warning" | "alert" }) {
  if (icon === "check") {
    return (
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="none">
        <path
          d="M3 8.5l3 3 7-7"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
    )
  }
  if (icon === "warning") {
    return (
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="none">
        <path
          d="M8 1.5l7 12.5H1L8 1.5z"
          stroke="currentColor"
          strokeWidth="1.5"
          strokeLinejoin="round"
        />
        <path d="M8 6.5v3.2" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
        <circle cx="8" cy="12" r="0.9" fill="currentColor" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" fill="none">
      <circle cx="8" cy="8" r="6.5" stroke="currentColor" strokeWidth="1.5" />
      <path d="M8 4.8v4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" />
      <circle cx="8" cy="11.2" r="0.9" fill="currentColor" />
    </svg>
  )
}

export function SeverityBadge({ severity }: { severity: Severity }) {
  const meta = severityMeta(severity)
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-xs font-medium"
      style={{
        color: `var(${meta.colorVar})`,
        borderColor: `var(${meta.colorVar})`,
      }}
    >
      <Icon icon={meta.icon} />
      {meta.label}
    </span>
  )
}
