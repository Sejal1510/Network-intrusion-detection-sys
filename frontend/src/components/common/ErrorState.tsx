/**
 * Failure state for a data panel/table. `role="alert"` is enough on its own
 * for screen readers -- every call site renders this conditionally (never
 * present at initial mount), so mounting it is itself the announcement;
 * no separate aria-live region needed.
 */
export function ErrorState({ message }: { message: string }) {
  return (
    <div
      role="alert"
      className="flex items-start gap-2.5 rounded-lg border p-3.5 text-sm"
      style={{
        borderColor: "color-mix(in srgb, var(--status-critical) 32%, var(--border-hairline))",
        backgroundColor: "color-mix(in srgb, var(--status-critical) 7%, transparent)",
      }}
    >
      <svg
        viewBox="0 0 20 20"
        width="18"
        height="18"
        fill="none"
        aria-hidden="true"
        className="mt-0.5 shrink-0"
        style={{ color: "var(--status-critical)" }}
      >
        <circle cx="10" cy="10" r="7.5" stroke="currentColor" strokeWidth="1.6" />
        <path d="M10 6.2v4.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
        <circle cx="10" cy="13.6" r="1" fill="currentColor" />
      </svg>
      <p className="text-[var(--text-primary)]">{message}</p>
    </div>
  )
}
