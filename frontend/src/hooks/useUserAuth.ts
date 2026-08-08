import { useCallback, useEffect, useState } from "react"
import { getCurrentUser, login as loginRequest, logout as logoutRequest } from "@/api/endpoints/auth"
import { ApiError, setSessionToken } from "@/api/client"
import type { UserRole } from "@/api/types"

const STORAGE_KEY = "nids_session_token"

export type UserAuthStatus = "anonymous" | "loading" | "authenticated"

export interface CurrentUser {
  username: string
  role: UserRole
}

export interface UserAuthState {
  status: UserAuthStatus
  user: CurrentUser | null
  token: string | null
  error: string | null
  login: (username: string, password: string) => Promise<void>
  logout: () => Promise<void>
}

/**
 * Real login for the dashboard (see docs/AUTH.md), independent of and
 * parallel to useDeviceAuth's anonymous device pairing -- a browser
 * operator proving who they are is a different concern from the
 * dashboard's own device identity for /ws/live.
 */
export function useUserAuth(): UserAuthState {
  const [token, setToken] = useState<string | null>(() =>
    typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEY)
  )
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [status, setStatus] = useState<UserAuthStatus>(token ? "loading" : "anonymous")
  const [error, setError] = useState<string | null>(null)

  // Rehydrate on mount if a token is stored -- verify it's still valid
  // via GET /auth/me rather than trusting localStorage blindly (the
  // session may have expired or been revoked server-side since).
  useEffect(() => {
    if (!token) return
    setSessionToken(token)
    getCurrentUser()
      .then((me) => {
        setUser({ username: me.username, role: me.role })
        setStatus("authenticated")
      })
      .catch(() => {
        window.localStorage.removeItem(STORAGE_KEY)
        setSessionToken(null)
        setToken(null)
        setStatus("anonymous")
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const login = useCallback(async (username: string, password: string): Promise<void> => {
    setStatus("loading")
    setError(null)
    try {
      const response = await loginRequest({ username, password })
      window.localStorage.setItem(STORAGE_KEY, response.token)
      setSessionToken(response.token)
      setToken(response.token)
      setUser({ username: response.username, role: response.role })
      setStatus("authenticated")
    } catch (err) {
      setStatus("anonymous")
      setError(
        err instanceof ApiError && err.status === 401
          ? "Invalid username or password."
          : "Login failed."
      )
      throw err
    }
  }, [])

  const logout = useCallback(async (): Promise<void> => {
    try {
      await logoutRequest()
    } catch {
      // best-effort -- the session is cleared client-side regardless
    }
    window.localStorage.removeItem(STORAGE_KEY)
    setSessionToken(null)
    setToken(null)
    setUser(null)
    setStatus("anonymous")
  }, [])

  return { status, user, token, error, login, logout }
}
