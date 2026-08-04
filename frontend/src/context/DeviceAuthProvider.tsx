import { createContext, useContext, type ReactNode } from "react"
import { useDeviceAuth, type DeviceAuthState } from "@/hooks/useDeviceAuth"

const DeviceAuthContext = createContext<DeviceAuthState | null>(null)

export function DeviceAuthProvider({ children }: { children: ReactNode }) {
  const state = useDeviceAuth()
  return <DeviceAuthContext.Provider value={state}>{children}</DeviceAuthContext.Provider>
}

export function useDeviceAuthContext(): DeviceAuthState {
  const context = useContext(DeviceAuthContext)
  if (!context) {
    throw new Error("useDeviceAuthContext must be used within a DeviceAuthProvider")
  }
  return context
}
