import { useState } from "react"

export function LoginForm({
  onSubmit,
  submitting,
  error,
}: {
  onSubmit: (username: string, password: string) => void
  submitting?: boolean
  error?: string | null
}) {
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(username, password)
      }}
      className="space-y-4"
    >
      <label className="block text-sm">
        <span className="mb-1 block text-[var(--text-secondary)]">Username</span>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
          className="w-full rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-3 py-2 text-sm"
        />
      </label>
      <label className="block text-sm">
        <span className="mb-1 block text-[var(--text-secondary)]">Password</span>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          className="w-full rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-3 py-2 text-sm"
        />
      </label>

      {error && (
        <p className="text-sm" style={{ color: "var(--status-critical)" }}>
          {error}
        </p>
      )}

      <button
        type="submit"
        disabled={submitting}
        className="w-full rounded bg-[var(--text-primary)] px-4 py-2 text-sm font-medium text-[var(--surface-page)] disabled:opacity-50"
      >
        {submitting ? "Signing in…" : "Sign in"}
      </button>
    </form>
  )
}
