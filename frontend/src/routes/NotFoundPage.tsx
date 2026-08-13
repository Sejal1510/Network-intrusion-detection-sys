import { Link, useLocation } from "react-router-dom"
import { Card } from "@/components/common/Card"
import { buttonClassName } from "@/components/common/Button"

export function NotFoundPage() {
  const location = useLocation()

  return (
    <div className="flex min-h-[60vh] items-center justify-center py-12">
      <Card interactive={false} className="w-full max-w-md space-y-5 text-center">
        <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-full border border-[color-mix(in_srgb,var(--status-warning)_40%,var(--border-hairline))] bg-[color-mix(in_srgb,var(--status-warning)_10%,transparent)]">
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="var(--status-warning)" strokeWidth="1.6" aria-hidden="true">
            <circle cx="6" cy="12" r="2" />
            <circle cx="18" cy="12" r="2" />
            <path d="M8.5 12h2M13.5 12h2" strokeLinecap="round" />
          </svg>
        </div>

        <div className="space-y-1.5">
          <p className="font-mono text-[10px] uppercase tracking-[0.14em] text-[var(--text-muted)]">
            No route matched
          </p>
          <h2 className="text-lg font-semibold text-[var(--text-primary)]">
            This segment isn&rsquo;t being monitored.
          </h2>
          <p className="text-sm text-[var(--text-secondary)]">
            <code className="font-mono text-xs text-[var(--text-muted)]">{location.pathname}</code> doesn&rsquo;t
            map to anything in this console.
          </p>
        </div>

        <Link to="/" className={buttonClassName("primary")}>
          Back to Overview
        </Link>
      </Card>
    </div>
  )
}
