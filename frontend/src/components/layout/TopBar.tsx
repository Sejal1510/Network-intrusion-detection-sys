import { useHealth } from "@/hooks/useHealth"
import { useModelInfo } from "@/hooks/useModelInfo"

export function TopBar() {
  const { data: health } = useHealth()
  const { data: model } = useModelInfo()

  return (
    <header className="flex items-center justify-between border-b border-[var(--border-hairline)] px-6 py-3">
      <div>
        <h1 className="text-sm font-semibold text-[var(--text-primary)]">NIDS Dashboard</h1>
        {model && (
          <p className="text-xs text-[var(--text-muted)]">
            Serving {model.model_name} ({model.run_id})
          </p>
        )}
      </div>
      <div className="flex items-center gap-2 text-xs">
        <span
          className="h-2 w-2 rounded-full"
          style={{
            backgroundColor: health?.model_loaded
              ? "var(--status-good)"
              : "var(--status-critical)",
          }}
          aria-hidden="true"
        />
        <span className="text-[var(--text-secondary)]">
          {health?.model_loaded ? "Model loaded" : "Model unavailable"}
        </span>
      </div>
    </header>
  )
}
