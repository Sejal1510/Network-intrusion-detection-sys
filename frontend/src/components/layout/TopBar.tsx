import type { RefObject } from "react"
import { useHealth } from "@/hooks/useHealth"
import { useModelInfo } from "@/hooks/useModelInfo"
import { useUserAuthContext } from "@/context/UserAuthProvider"

export function TopBar({
  menuButtonRef,
  mobileNavOpen,
  onToggleMobileNav,
}: {
  menuButtonRef: RefObject<HTMLButtonElement | null>
  mobileNavOpen: boolean
  onToggleMobileNav: () => void
}) {
  const { data: health } = useHealth()
  const { data: model } = useModelInfo()
  const { user, logout } = useUserAuthContext()

  return (
    <header className="surface-glass flex items-center justify-between gap-3 border-b border-[var(--border-hairline)] px-4 py-3 shadow-[inset_0_1px_0_var(--border-soft)] sm:px-6">
      <div className="flex min-w-0 items-center gap-3">
        <button
          ref={menuButtonRef}
          type="button"
          onClick={onToggleMobileNav}
          aria-label={mobileNavOpen ? "Close navigation menu" : "Open navigation menu"}
          aria-expanded={mobileNavOpen}
          aria-controls="mobile-sidebar"
          className="-ml-1 flex h-9 w-9 shrink-0 items-center justify-center rounded-md text-[var(--text-secondary)] transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_8%,transparent)] hover:text-[var(--text-primary)] md:hidden"
        >
          <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
            {mobileNavOpen ? (
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            ) : (
              <path d="M4 6h16M4 12h16M4 18h16" strokeLinecap="round" />
            )}
          </svg>
        </button>
        <div className="min-w-0">
          <h1 className="truncate font-mono text-sm font-semibold tracking-wide text-[var(--text-primary)]">NIDS Dashboard</h1>
          {model && (
            <p className="truncate text-xs text-[var(--text-muted)]">
              Serving {model.model_name} ({model.run_id})
            </p>
          )}
        </div>
      </div>
      <div className="flex flex-wrap items-center justify-end gap-x-3 gap-y-1 text-xs sm:gap-x-4">
        <div className="flex items-center gap-2">
          <span
            className={`h-2 w-2 rounded-full ${health?.model_loaded ? "animate-[pulse-ring_2.4s_ease-out_infinite]" : ""}`}
            style={{
              backgroundColor: health?.model_loaded ? "var(--status-good)" : "var(--status-critical)",
            }}
            aria-hidden="true"
          />
          <span className="text-[var(--text-secondary)]">
            {health?.model_loaded ? "Model loaded" : "Model unavailable"}
          </span>
        </div>
        {user && (
          <div className="flex items-center gap-2 border-l border-[var(--border-hairline)] pl-4">
            <span className="text-[var(--text-secondary)]">
              {user.username} ({user.role})
            </span>
            <button
              type="button"
              onClick={() => void logout()}
              className="rounded border border-[var(--border-hairline)] px-2 py-1 text-[var(--text-secondary)] transition-colors hover:text-[var(--text-primary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_6%,transparent)]"
            >
              Sign out
            </button>
          </div>
        )}
      </div>
    </header>
  )
}
