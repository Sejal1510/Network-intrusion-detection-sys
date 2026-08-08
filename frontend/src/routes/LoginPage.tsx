import { useState } from "react"
import { Navigate, useLocation, useNavigate } from "react-router-dom"
import { LoginForm } from "@/components/auth/LoginForm"
import { useUserAuthContext } from "@/context/UserAuthProvider"

export function LoginPage() {
  const { status, error, login } = useUserAuthContext()
  const navigate = useNavigate()
  const location = useLocation()
  const [submitting, setSubmitting] = useState(false)

  if (status === "authenticated") {
    const redirectTo = (location.state as { from?: string } | null)?.from ?? "/"
    return <Navigate to={redirectTo} replace />
  }

  async function handleSubmit(username: string, password: string) {
    setSubmitting(true)
    try {
      await login(username, password)
      const redirectTo = (location.state as { from?: string } | null)?.from ?? "/"
      navigate(redirectTo, { replace: true })
    } catch {
      // useUserAuth already recorded a user-facing message in `error`.
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="flex min-h-svh items-center justify-center p-6">
      <div className="w-full max-w-sm space-y-6 rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)] p-6">
        <div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">NIDS Dashboard</h1>
          <p className="text-sm text-[var(--text-secondary)]">Sign in to continue.</p>
        </div>
        <LoginForm onSubmit={handleSubmit} submitting={submitting} error={error} />
      </div>
    </div>
  )
}
