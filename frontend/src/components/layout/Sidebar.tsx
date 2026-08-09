import { useEffect, useRef, type ReactNode } from "react"
import { NavLink } from "react-router-dom"
import { useUserAuthContext } from "@/context/UserAuthProvider"

const ICONS: Record<string, ReactNode> = {
  "/": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="3" y="3" width="7" height="7" rx="1.5" />
      <rect x="14" y="3" width="7" height="7" rx="1.5" />
      <rect x="3" y="14" width="7" height="7" rx="1.5" />
      <rect x="14" y="14" width="7" height="7" rx="1.5" />
    </svg>
  ),
  "/alerts": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M12 3 2 20h20L12 3Z" strokeLinejoin="round" />
      <path d="M12 10v4" strokeLinecap="round" />
      <circle cx="12" cy="17" r="0.6" fill="currentColor" stroke="none" />
    </svg>
  ),
  "/history": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="12" cy="12" r="8.5" />
      <path d="M12 7.5V12l3 2" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  "/predict": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <circle cx="12" cy="12" r="2.2" />
      <path
        d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"
        strokeLinecap="round"
      />
    </svg>
  ),
  "/upload": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M12 15V4M8 8l4-4 4 4" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M4 15v3a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-3" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  ),
  "/audit": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="4" y="3" width="16" height="18" rx="1.5" />
      <path d="M8 8h8M8 12h8M8 16h5" strokeLinecap="round" />
    </svg>
  ),
  "/metrics": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <path d="M4 20V10M11 20V4M18 20v-7" strokeLinecap="round" />
    </svg>
  ),
  "/devices": (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6">
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <path d="M9 3v3M15 3v3M9 18v3M15 18v3M3 9h3M3 15h3M18 9h3M18 15h3" strokeLinecap="round" />
    </svg>
  ),
}

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/alerts", label: "Alerts" },
  { to: "/history", label: "History" },
  { to: "/predict", label: "Manual Predict" },
  { to: "/upload", label: "CSV Upload" },
  { to: "/audit", label: "Audit Log" },
  { to: "/metrics", label: "Metrics" },
]

type Link = (typeof LINKS)[number]

function NavLinks({ links, onNavigate }: { links: Link[]; onNavigate?: () => void }) {
  return (
    <>
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end}
          onClick={onNavigate}
          className={({ isActive }) =>
            `group relative flex items-center gap-2.5 rounded-md py-2 pl-3.5 pr-2 text-sm transition-colors before:absolute before:left-0 before:top-1.5 before:bottom-1.5 before:w-[3px] before:rounded-full before:bg-[var(--accent)] before:transition-all ${
              isActive
                ? "bg-[color-mix(in_srgb,var(--accent)_12%,transparent)] font-medium text-[var(--text-primary)] before:scale-y-100 before:opacity-100"
                : "text-[var(--text-secondary)] before:scale-y-50 before:opacity-0 hover:text-[var(--text-primary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_5%,transparent)]"
            }`
          }
        >
          <span className="h-4 w-4 shrink-0 opacity-85">{ICONS[link.to]}</span>
          {link.label}
        </NavLink>
      ))}
    </>
  )
}

/**
 * Renders two physically separate <nav> elements rather than one nav that's
 * repositioned by breakpoint: the desktop rail (`hidden md:flex`) keeps the
 * pre-existing markup/classes untouched below, and the off-canvas mobile
 * panel (`md:hidden`) owns its own open/close lifecycle. Below md, the
 * panel is always mounted but `visibility: hidden` (see `.mobile-nav-panel`
 * in index.css) while closed, so its links drop out of the tab order and
 * the accessibility tree instead of merely sliding off-screen.
 */
export function Sidebar({
  open,
  onNavigate,
  onDismiss,
}: {
  open: boolean
  /** A nav link was clicked -- close, but don't steal focus (it's moving with the route). */
  onNavigate: () => void
  /** Backdrop click / close button -- close and return focus to the menu toggle. */
  onDismiss: () => void
}) {
  const { user } = useUserAuthContext()
  const links = user?.role === "admin" ? [...LINKS, { to: "/devices", label: "Devices" }] : LINKS
  const closeButtonRef = useRef<HTMLButtonElement>(null)

  useEffect(() => {
    if (open) closeButtonRef.current?.focus()
  }, [open])

  return (
    <>
      <nav className="surface-glass hidden w-48 shrink-0 flex-col gap-1 border-r border-[var(--border-hairline)] p-4 shadow-[inset_-1px_0_0_var(--border-soft)] md:flex">
        <NavLinks links={links} />
      </nav>

      {open && (
        <div
          className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px] md:hidden"
          aria-hidden="true"
          onClick={onDismiss}
        />
      )}

      <nav
        id="mobile-sidebar"
        aria-label="Main navigation"
        className={`mobile-nav-panel fixed inset-y-0 left-0 z-50 flex w-72 max-w-[85vw] flex-col gap-1 border-r border-[var(--border-hairline)] bg-[var(--surface-elevated)] p-4 shadow-[var(--shadow-hover)] md:hidden ${
          open ? "is-open" : ""
        }`}
      >
        <div className="mb-2 flex items-center justify-between">
          <span className="font-mono text-xs font-semibold uppercase tracking-wide text-[var(--text-muted)]">
            Navigation
          </span>
          <button
            ref={closeButtonRef}
            type="button"
            onClick={onDismiss}
            aria-label="Close navigation menu"
            className="flex h-8 w-8 items-center justify-center rounded-md text-[var(--text-secondary)] transition-colors hover:bg-[color-mix(in_srgb,var(--text-primary)_8%,transparent)] hover:text-[var(--text-primary)]"
          >
            <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden="true">
              <path d="M6 6l12 12M18 6L6 18" strokeLinecap="round" />
            </svg>
          </button>
        </div>
        <NavLinks links={links} onNavigate={onNavigate} />
      </nav>
    </>
  )
}
