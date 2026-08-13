import type { InputHTMLAttributes } from "react"

/**
 * Accessible custom checkbox -- same recipe as FilterSelect: keep the real
 * <input type="checkbox"> for native keyboard/screen-reader semantics
 * (visually hidden via `sr-only`, not display:none or removed), and drive
 * a styled sibling via Tailwind's `peer-*` variants for the visible box.
 * Focus-visible has to be re-declared here because index.css's global
 * `input:focus-visible` rule outlines the (invisible) real input, not the
 * box a sighted user actually sees.
 */
export function Checkbox({
  label,
  id,
  className = "",
  ...rest
}: InputHTMLAttributes<HTMLInputElement> & { label: string; id: string }) {
  return (
    <label
      htmlFor={id}
      className={`inline-flex cursor-pointer items-center gap-2 text-sm text-[var(--text-secondary)] ${className}`}
    >
      <span className="relative inline-flex h-4 w-4 shrink-0 items-center justify-center">
        <input id={id} type="checkbox" className="peer sr-only" {...rest} />
        <span
          aria-hidden="true"
          className="h-4 w-4 rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] transition-colors peer-checked:border-[var(--accent)] peer-checked:bg-[var(--accent)] peer-focus-visible:outline peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2 peer-focus-visible:outline-[var(--accent)]"
        />
        <svg
          viewBox="0 0 16 16"
          width="10"
          height="10"
          fill="none"
          aria-hidden="true"
          className="pointer-events-none absolute text-[var(--accent-contrast)] opacity-0 transition-opacity peer-checked:opacity-100"
        >
          <path
            d="M3 8.5l3 3 7-7"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
      {label}
    </label>
  )
}
