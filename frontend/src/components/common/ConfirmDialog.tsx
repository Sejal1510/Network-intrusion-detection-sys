import { useEffect, useId, useRef } from "react"
import { Button } from "@/components/common/Button"

/**
 * Hand-rolled modal, not the native <dialog> element -- mirrors the exact
 * backdrop/Esc/focus-management/scroll-lock pattern AppShell+Sidebar
 * already use for the mobile nav panel, so there's no new dependency and
 * no reliance on <dialog>'s showModal()/close() imperative API. Always
 * mounted-when-shown (the caller conditionally renders it), rather than
 * taking an `open` prop -- setup/teardown lives in a single mount effect.
 */
export function ConfirmDialog({
  title,
  description,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  danger = false,
  pending = false,
  onConfirm,
  onCancel,
}: {
  title: string
  description: string
  confirmLabel?: string
  cancelLabel?: string
  /** Destructive action -- confirm button renders in the critical/danger variant. */
  danger?: boolean
  pending?: boolean
  onConfirm: () => void
  onCancel: () => void
}) {
  const titleId = useId()
  const descriptionId = useId()
  const cancelButtonRef = useRef<HTMLButtonElement>(null)
  const previouslyFocusedRef = useRef<HTMLElement | null>(null)

  useEffect(() => {
    previouslyFocusedRef.current = document.activeElement as HTMLElement | null
    cancelButtonRef.current?.focus()

    const previousOverflow = document.body.style.overflow
    document.body.style.overflow = "hidden"

    function onKeyDown(event: KeyboardEvent) {
      if (event.key === "Escape") onCancel()
    }
    document.addEventListener("keydown", onKeyDown)

    return () => {
      document.body.style.overflow = previousOverflow
      document.removeEventListener("keydown", onKeyDown)
      previouslyFocusedRef.current?.focus()
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50 backdrop-blur-[2px]" aria-hidden="true" onClick={onCancel} />
      <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
        <div
          role="alertdialog"
          aria-modal="true"
          aria-labelledby={titleId}
          aria-describedby={descriptionId}
          className="card w-full max-w-sm space-y-4 p-5"
        >
          <div className="space-y-1.5">
            <h2 id={titleId} className="text-base font-semibold text-[var(--text-primary)]">
              {title}
            </h2>
            <p id={descriptionId} className="text-sm text-[var(--text-secondary)]">
              {description}
            </p>
          </div>
          <div className="flex items-center justify-end gap-2">
            <Button ref={cancelButtonRef} variant="secondary" onClick={onCancel} disabled={pending}>
              {cancelLabel}
            </Button>
            <Button variant={danger ? "danger" : "primary"} onClick={onConfirm} disabled={pending}>
              {pending ? "Working…" : confirmLabel}
            </Button>
          </div>
        </div>
      </div>
    </>
  )
}
