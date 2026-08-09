import { useCallback, useEffect, useState } from "react"

export type ThemePreference = "system" | "light" | "dark"

const STORAGE_KEY = "nids-theme"

function readStoredPreference(): ThemePreference {
  if (typeof window === "undefined") return "system"
  const stored = window.localStorage.getItem(STORAGE_KEY)
  return stored === "light" || stored === "dark" ? stored : "system"
}

function applyPreference(preference: ThemePreference) {
  const root = document.documentElement
  if (preference === "system") {
    root.removeAttribute("data-theme")
    window.localStorage.removeItem(STORAGE_KEY)
  } else {
    root.setAttribute("data-theme", preference)
    window.localStorage.setItem(STORAGE_KEY, preference)
  }
}

/**
 * Manual override on top of the OS `prefers-color-scheme` default (see
 * index.css's `[data-theme]` hooks). "system" is the resting state -- no
 * attribute, no storage entry -- so a user who never touches the toggle
 * behaves exactly as before this existed. `index.html` applies any stored
 * override synchronously pre-paint so there's no flash on reload.
 */
export function useTheme() {
  const [preference, setPreference] = useState<ThemePreference>(readStoredPreference)

  useEffect(() => {
    applyPreference(preference)
  }, [preference])

  const cycle = useCallback(() => {
    setPreference((prev) => (prev === "system" ? "light" : prev === "light" ? "dark" : "system"))
  }, [])

  return { preference, cycle }
}
