import { Suspense, useEffect, useRef, useState } from "react"
import { Outlet, useLocation } from "react-router-dom"
import { Sidebar } from "@/components/layout/Sidebar"
import { TopBar } from "@/components/layout/TopBar"
import { NetworkBackground } from "@/components/layout/NetworkBackground"
import { RouteLoadingFallback } from "@/components/common/RouteLoadingFallback"

export function AppShell() {
  const location = useLocation()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const menuButtonRef = useRef<HTMLButtonElement>(null)

  // Close on every route change. Focus is left alone here -- it's moving
  // with the navigation, not being dismissed -- unlike closeAndReturnFocus.
  useEffect(() => {
    setMobileNavOpen(false)
  }, [location.pathname])

  // If the viewport grows past the mobile breakpoint mid-session, drop the
  // off-canvas state so it can't linger into the desktop layout.
  useEffect(() => {
    const query = window.matchMedia("(min-width: 768px)")
    function onChange() {
      if (query.matches) setMobileNavOpen(false)
    }
    query.addEventListener("change", onChange)
    return () => query.removeEventListener("change", onChange)
  }, [])

  useEffect(() => {
    if (!mobileNavOpen) return
    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") {
        setMobileNavOpen(false)
        menuButtonRef.current?.focus()
      }
    }
    document.addEventListener("keydown", onKeyDown)
    return () => document.removeEventListener("keydown", onKeyDown)
  }, [mobileNavOpen])

  // Lock background scroll while the off-canvas nav is open.
  useEffect(() => {
    if (!mobileNavOpen) return
    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"
    return () => {
      document.body.style.overflow = previousOverflow
    }
  }, [mobileNavOpen])

  function closeMobileNavAndReturnFocus() {
    setMobileNavOpen(false)
    menuButtonRef.current?.focus()
  }

  return (
    <div className="relative flex min-h-svh flex-col overflow-x-hidden">
      <NetworkBackground />
      <div className="relative z-10 flex min-h-svh flex-col">
        <TopBar
          menuButtonRef={menuButtonRef}
          mobileNavOpen={mobileNavOpen}
          onToggleMobileNav={() => setMobileNavOpen((v) => !v)}
        />
        <div className="flex min-w-0 flex-1">
          <Sidebar
            open={mobileNavOpen}
            onNavigate={() => setMobileNavOpen(false)}
            onDismiss={closeMobileNavAndReturnFocus}
          />
          <main className="min-w-0 flex-1 p-4 sm:p-6">
            <div key={location.pathname} className="route-transition">
              <Suspense fallback={<RouteLoadingFallback />}>
                <Outlet />
              </Suspense>
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}
