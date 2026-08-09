import { useRef, type HTMLAttributes, type MouseEvent, type ReactNode } from "react"
import { useReducedMotion } from "@/hooks/useReducedMotion"

export interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  /** Pointer-tracked sheen + hover lift. Default true -- set false for static containers. */
  interactive?: boolean
  /** Subdued treatment for reference/config content that isn't a live metric (no lift, no shadow). */
  quiet?: boolean
  /** Thin top-edge accent line, e.g. a stat tile reporting an attack count. */
  accent?: "good" | "critical"
  padding?: string
}

/**
 * Shared bordered-surface primitive replacing the app's previously ad hoc
 * `rounded-lg border border-[var(--border-hairline)] bg-[var(--surface-card)]
 * p-4` divs (StatTile, chart cards, PredictionResultCard, etc). Owns the
 * pointer-reactive hover sheen so it isn't reimplemented per component.
 */
export function Card({
  children,
  interactive = true,
  quiet = false,
  accent,
  padding = "p-4",
  className = "",
  onMouseMove,
  ...rest
}: CardProps) {
  const ref = useRef<HTMLDivElement>(null)
  const reducedMotion = useReducedMotion()
  const illuminated = interactive && !quiet && !reducedMotion

  function handleMouseMove(event: MouseEvent<HTMLDivElement>) {
    const el = ref.current
    if (el) {
      const rect = el.getBoundingClientRect()
      el.style.setProperty("--mx", `${((event.clientX - rect.left) / rect.width) * 100}%`)
      el.style.setProperty("--my", `${((event.clientY - rect.top) / rect.height) * 100}%`)
    }
    onMouseMove?.(event)
  }

  const classes = [
    "card",
    quiet ? "card--quiet" : interactive ? "card--interactive" : "",
    accent === "good" ? "card--accent-good" : "",
    accent === "critical" ? "card--accent-critical" : "",
    padding,
    className,
  ]
    .filter(Boolean)
    .join(" ")

  return (
    <div ref={ref} className={classes} onMouseMove={illuminated ? handleMouseMove : onMouseMove} {...rest}>
      {children}
    </div>
  )
}
