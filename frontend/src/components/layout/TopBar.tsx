import { useHealth } from "@/hooks/useHealth"
import { useModelInfo } from "@/hooks/useModelInfo"
import { useUserAuthContext } from "@/context/UserAuthProvider"

export function TopBar() {
  const { data: health } = useHealth()
  const { data: model } = useModelInfo()
  const { user, logout } = useUserAuthContext()

  return (
    <header className="surface-glass flex items-center justify-between border-b border-[var(--border-hairline)] px-6 py-3 shadow-[inset_0_1px_0_var(--border-soft)]">
      <div>
        <h1 className="font-mono text-sm font-semibold tracking-wide text-[var(--text-primary)]">NIDS Dashboard</h1>
        {model && (
          <p className="text-xs text-[var(--text-muted)]">
            Serving {model.model_name} ({model.run_id})
          </p>
        )}
      </div>
      <div className="flex items-center gap-4 text-xs">
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
