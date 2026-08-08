import { createContext, useContext, type ReactNode } from "react"
import { useUserAuth, type UserAuthState } from "@/hooks/useUserAuth"

const UserAuthContext = createContext<UserAuthState | null>(null)

export function UserAuthProvider({ children }: { children: ReactNode }) {
  const state = useUserAuth()
  return <UserAuthContext.Provider value={state}>{children}</UserAuthContext.Provider>
}

export function useUserAuthContext(): UserAuthState {
  const context = useContext(UserAuthContext)
  if (!context) {
    throw new Error("useUserAuthContext must be used within a UserAuthProvider")
  }
  return context
}
