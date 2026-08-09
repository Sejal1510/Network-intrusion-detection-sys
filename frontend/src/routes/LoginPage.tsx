import { useState } from "react"
import { Navigate, useLocation, useNavigate } from "react-router-dom"
import { LoginForm } from "@/components/auth/LoginForm"
import { Card } from "@/components/common/Card"
import { NetworkBackground } from "@/components/layout/NetworkBackground"
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
    <div className="relative flex min-h-svh items-center justify-center p-6">
      <NetworkBackground />
      <Card interactive={false} className="relative z-10 w-full max-w-sm space-y-6">
        <div>
          <h1 className="font-mono text-lg font-semibold tracking-wide text-[var(--text-primary)]">
            NIDS Dashboard
          </h1>
          <p className="text-sm text-[var(--text-secondary)]">Sign in to continue.</p>
        </div>
        <LoginForm onSubmit={handleSubmit} submitting={submitting} error={error} />
      </Card>
    </div>
  )
}
