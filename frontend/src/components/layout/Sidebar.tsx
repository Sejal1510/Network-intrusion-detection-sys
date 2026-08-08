import { NavLink } from "react-router-dom"
import { useUserAuthContext } from "@/context/UserAuthProvider"

const LINKS = [
  { to: "/", label: "Overview", end: true },
  { to: "/alerts", label: "Alerts" },
  { to: "/history", label: "History" },
  { to: "/predict", label: "Manual Predict" },
  { to: "/upload", label: "CSV Upload" },
]

export function Sidebar() {
  const { user } = useUserAuthContext()
  const links = user?.role === "admin" ? [...LINKS, { to: "/devices", label: "Devices" }] : LINKS

  return (
    <nav className="flex w-48 shrink-0 flex-col gap-1 border-r border-[var(--border-hairline)] p-4">
      {links.map((link) => (
        <NavLink
          key={link.to}
          to={link.to}
          end={link.end}
          className={({ isActive }) =>
            `rounded px-3 py-2 text-sm ${
              isActive
                ? "bg-[var(--gridline)] font-medium text-[var(--text-primary)]"
                : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            }`
          }
        >
          {link.label}
        </NavLink>
      ))}
    </nav>
  )
}
