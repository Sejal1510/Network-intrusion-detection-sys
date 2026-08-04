import type { MitreMapping } from "@/api/types"

export function MitreChip({ mitre }: { mitre: MitreMapping }) {
  return (
    <div className="flex flex-wrap items-center gap-1.5">
      <span className="text-xs text-[var(--text-muted)]">{mitre.tactic}</span>
      {mitre.techniques.map((technique) => (
        <a
          key={technique.id}
          href={technique.url}
          target="_blank"
          rel="noreferrer"
          title={technique.name}
          className="rounded border border-[var(--border-hairline)] px-1.5 py-0.5 text-xs text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          {technique.id}
        </a>
      ))}
    </div>
  )
}
