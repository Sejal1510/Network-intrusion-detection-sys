import type { SelectHTMLAttributes } from "react"

/**
 * Drop-in replacement for a plain `<select>` filter control -- same props,
 * same native semantics (keyboard, screen reader, native popup), just
 * `appearance-none` plus a custom chevron so the browser's default select
 * chrome doesn't show through the Sentinel surface/token system. Focus
 * styling comes from the global `select:focus-visible` rule in index.css.
 */
export function FilterSelect({ className = "", children, ...rest }: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <span className="relative inline-flex">
      <select
        {...rest}
        className={`appearance-none rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] py-1 pl-2 pr-7 text-sm text-[var(--text-primary)] transition-colors hover:border-[color-mix(in_srgb,var(--accent)_35%,var(--border-hairline))] ${className}`}
      >
        {children}
      </select>
      <svg
        viewBox="0 0 16 16"
        width="12"
        height="12"
        fill="none"
        aria-hidden="true"
        className="pointer-events-none absolute right-2 top-1/2 -translate-y-1/2 text-[var(--text-muted)]"
      >
        <path d="M4 6l4 4 4-4" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    </span>
  )
}
