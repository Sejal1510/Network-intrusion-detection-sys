import { Navigate, Outlet, useLocation } from "react-router-dom"
import { useUserAuthContext } from "@/context/UserAuthProvider"
import type { UserRole } from "@/api/types"

/**
 * Gates the routes nested under it on login status (and optionally role).
 * "loading" covers both an in-flight GET /auth/me rehydration and an
 * in-flight login submission -- render nothing rather than bouncing to
 * /login and back once the token turns out to be valid.
 */
export function RequireAuth({ role }: { role?: UserRole }) {
  const { status, user } = useUserAuthContext()
  const location = useLocation()

  if (status === "loading") return null

  if (status === "anonymous") {
    return <Navigate to="/login" replace state={{ from: location.pathname }} />
  }

  if (role && user?.role !== role) {
    return <Navigate to="/" replace />
  }

  return <Outlet />
}
