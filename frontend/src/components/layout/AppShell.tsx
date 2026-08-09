import { Outlet, useLocation } from "react-router-dom"
import { Sidebar } from "@/components/layout/Sidebar"
import { TopBar } from "@/components/layout/TopBar"
import { NetworkBackground } from "@/components/layout/NetworkBackground"

export function AppShell() {
  const location = useLocation()

  return (
    <div className="relative flex min-h-svh flex-col">
      <NetworkBackground />
      <div className="relative z-10 flex min-h-svh flex-col">
        <TopBar />
        <div className="flex flex-1">
          <Sidebar />
          <main className="flex-1 p-6">
            <div key={location.pathname} className="route-transition">
              <Outlet />
            </div>
          </main>
        </div>
      </div>
    </div>
  )
}
