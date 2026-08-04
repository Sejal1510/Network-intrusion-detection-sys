import { useCallback, useRef, useState } from "react"
import { exchangePairingToken, requestPairingToken } from "@/api/endpoints/agent"
import { ApiError } from "@/api/client"

const STORAGE_KEY = "nids_device_token"
const DEVICE_NAME = "dashboard-web"

export type DeviceAuthStatus = "unpaired" | "pairing" | "ready" | "unavailable"

export interface DeviceAuthState {
  status: DeviceAuthStatus
  token: string | null
  error: string | null
  /**
   * Pairs (if needed) and resolves with a device token. Safe to call from
   * multiple pages -- concurrent callers share the same in-flight pairing
   * request rather than each triggering their own POST /agent/pair.
   */
  ensurePaired: () => Promise<string>
}

/**
 * Reuses the agent-pairing flow (src/nids/api/agent_auth.py) as a stand-in
 * device identity for the dashboard -- there is no real user-login system
 * in this backend (see docs/DASHBOARD.md "Auth model"). Pairing is lazy:
 * this hook does nothing until ensurePaired() is called by a page that
 * actually needs a token (Live Feed/Alerts/History), so a browser tab that
 * never visits those pages never creates a device row.
 */
export function useDeviceAuth(): DeviceAuthState {
  const [token, setToken] = useState<string | null>(() =>
    typeof window === "undefined" ? null : window.localStorage.getItem(STORAGE_KEY)
  )
  const [status, setStatus] = useState<DeviceAuthStatus>(token ? "ready" : "unpaired")
  const [error, setError] = useState<string | null>(null)
  const inFlight = useRef<Promise<string> | null>(null)

  const ensurePaired = useCallback(async (): Promise<string> => {
    const existing = window.localStorage.getItem(STORAGE_KEY)
    if (existing) {
      setToken(existing)
      setStatus("ready")
      return existing
    }

    if (inFlight.current) return inFlight.current

    setStatus("pairing")
    setError(null)

    const pairingPromise = (async () => {
      try {
        const { pairing_token } = await requestPairingToken()
        const { token: deviceToken } = await exchangePairingToken(pairing_token, DEVICE_NAME)
        window.localStorage.setItem(STORAGE_KEY, deviceToken)
        setToken(deviceToken)
        setStatus("ready")
        return deviceToken
      } catch (err) {
        if (err instanceof ApiError && err.status === 503) {
          setStatus("unavailable")
          setError("This server has no database configured, so live streaming and history are unavailable.")
        } else {
          setStatus("unpaired")
          setError(err instanceof Error ? err.message : "Failed to pair with the server.")
        }
        throw err
      } finally {
        inFlight.current = null
      }
    })()

    inFlight.current = pairingPromise
    return pairingPromise
  }, [])

  return { status, token, error, ensurePaired }
}
