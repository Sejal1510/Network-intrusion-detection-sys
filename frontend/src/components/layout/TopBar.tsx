import type { RefObject } from "react"
import { useHealth } from "@/hooks/useHealth"
import { useModelInfo } from "@/hooks/useModelInfo"
import { useTheme, type ThemePreference } from "@/hooks/useTheme"
import { useUserAuthContext } from "@/context/UserAuthProvider"

const THEME_LABEL: Record<ThemePreference, string> = {
  system: "System",
  light: "Light",
  dark: "Dark",
}

const THEME_NEXT: Record<ThemePreference, ThemePreference> = {
  system: "light",
  light: "dark",
  dark: "system",
}

function ThemeIcon({ preference }: { preference: ThemePreference }) {
  if (preference === "light") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <circle cx="12" cy="12" r="4" />
        <path
          d="M12 3v2M12 19v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M3 12h2M19 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"
          strokeLinecap="round"
        />
      </svg>
    )
  }
  if (preference === "dark") {
    return (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
        <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a6.5 6.5 0 0 0 10.5 10.5Z" strokeLinejoin="round" />
      </svg>
    )
  }
  return (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
      <rect x="3" y="4" width="18" height="12" rx="1.5" />
      <path d="M8 20h8M12 16v4" strokeLinecap="round" />
    </svg>
  )
}

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
  const { preference, cycle } = useTheme()

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
        <button
          type="button"
          onClick={cycle}
          aria-label={`Theme: ${THEME_LABEL[preference]}. Activate to switch to ${THEME_LABEL[THEME_NEXT[preference]]}.`}
          title={`Theme: ${THEME_LABEL[preference]}`}
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md text-[var(--text-secondary)] transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_8%,transparent)] hover:text-[var(--text-primary)]"
        >
          <ThemeIcon preference={preference} />
        </button>
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
