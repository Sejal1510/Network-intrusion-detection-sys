import type { ButtonHTMLAttributes, Ref } from "react"

export type ButtonVariant = "primary" | "danger" | "secondary"

/**
 * Shared className builder so non-<button> elements (e.g. NotFoundPage's
 * <Link>) can carry the exact same primary/danger/secondary treatment as
 * real buttons, without forcing a polymorphic component.
 */
export function buttonClassName(variant: ButtonVariant, className = ""): string {
  const base =
    "inline-flex items-center justify-center gap-2 rounded-md px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50"
  const variants: Record<ButtonVariant, string> = {
    primary: "bg-[var(--accent)] text-[var(--accent-contrast)] hover:opacity-90",
    danger: "bg-[var(--status-critical)] text-[var(--accent-contrast)] hover:opacity-90",
    secondary:
      "border border-[var(--border-hairline)] text-[var(--text-secondary)] hover:bg-[color-mix(in_srgb,var(--text-primary)_6%,transparent)] hover:text-[var(--text-primary)]",
  }
  return `${base} ${variants[variant]} ${className}`
}

export function Button({
  variant = "primary",
  className = "",
  type = "button",
  ref,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; ref?: Ref<HTMLButtonElement> }) {
  return <button ref={ref} type={type} className={buttonClassName(variant, className)} {...rest} />
}
