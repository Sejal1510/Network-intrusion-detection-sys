export type ConnectionStatus = "connecting" | "live" | "reconnecting" | "offline"

const STATUS_META: Record<ConnectionStatus, { label: string; colorVar: string }> = {
  connecting: { label: "Connecting…", colorVar: "--status-warning" },
  live: { label: "Live", colorVar: "--status-good" },
  reconnecting: { label: "Reconnecting…", colorVar: "--status-warning" },
  offline: { label: "Offline", colorVar: "--status-critical" },
}

export function ConnectionStatusIndicator({ status }: { status: ConnectionStatus }) {
  const meta = STATUS_META[status]
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-[var(--text-secondary)]">
      <span
        className="h-2 w-2 rounded-full"
        style={{ backgroundColor: `var(${meta.colorVar})` }}
        aria-hidden="true"
      />
      {meta.label}
    </span>
  )
}
