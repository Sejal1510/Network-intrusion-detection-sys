import { useCallback, useEffect, useState } from "react"
import { useQueryClient } from "@tanstack/react-query"
import { getCurrentUser, login as loginRequest, logout as logoutRequest } from "@/api/endpoints/auth"
import { ApiError, setSessionToken, setUnauthorizedHandler } from "@/api/client"
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
 * Real login for the dashboard (see docs/AUTH.md). Also the identity
 * behind /ws/live: useLiveFeed mints a short-lived ws-ticket from this
 * same session immediately before every connect, so logging out (status
 * turning "anonymous" here) redirects away from any page holding a live
 * connection via RequireAuth, which unmounts it and closes the socket --
 * no separate teardown needed here.
 */
export function useUserAuth(): UserAuthState {
  const queryClient = useQueryClient()
  const [token, setToken] = useState<string | null>(() =>
    typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEY)
  )
  const [user, setUser] = useState<CurrentUser | null>(null)
  const [status, setStatus] = useState<UserAuthStatus>(token ? "loading" : "anonymous")
  const [error, setError] = useState<string | null>(null)

  // Shared by rehydration-failure, a mid-session 401, and manual logout --
  // all three mean "this browser no longer has a valid session," so all
  // three must leave state identically clean. Also clears the query cache
  // so a different user logging in on the same tab never sees a flash of
  // the previous user's cached alerts/history/devices before fresh
  // queries land.
  const clearLocalSession = useCallback(() => {
    window.localStorage.removeItem(STORAGE_KEY)
    setSessionToken(null)
    setToken(null)
    setUser(null)
    setStatus("anonymous")
    queryClient.clear()
  }, [queryClient])

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
      .catch(clearLocalSession)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // A request that carried a (previously valid) session token came back
  // 401 -- the session expired or was revoked server-side mid-use.
  // client.ts owns detecting this; this just reacts to it, the same way
  // RequireAuth already reacts to `status` turning "anonymous" by
  // redirecting to /login (no changes needed there).
  useEffect(() => {
    setUnauthorizedHandler(clearLocalSession)
    return () => setUnauthorizedHandler(null)
  }, [clearLocalSession])

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
    clearLocalSession()
  }, [clearLocalSession])

  return { status, user, token, error, login, logout }
}
