import { useState } from "react"
import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { ConfirmDialog } from "./ConfirmDialog"

describe("ConfirmDialog", () => {
  it("renders as an alertdialog labelled by its title and description", () => {
    render(
      <ConfirmDialog
        title="Revoke this device?"
        description="This can't be undone."
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )

    expect(screen.getByRole("alertdialog", { name: "Revoke this device?" })).toBeInTheDocument()
    expect(screen.getByText("This can't be undone.")).toBeInTheDocument()
  })

  it("calls onCancel on Escape", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<ConfirmDialog title="t" description="d" onConfirm={vi.fn()} onCancel={onCancel} />)

    await user.keyboard("{Escape}")

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it("calls onCancel when the backdrop is clicked", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const { container } = render(
      <ConfirmDialog title="t" description="d" onConfirm={vi.fn()} onCancel={onCancel} />
    )

    const backdrop = container.querySelector('[aria-hidden="true"]')
    expect(backdrop).not.toBeNull()
    await user.click(backdrop as Element)

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it("calls onCancel when the Cancel button is clicked", async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    render(<ConfirmDialog title="t" description="d" onConfirm={vi.fn()} onCancel={onCancel} />)

    await user.click(screen.getByRole("button", { name: "Cancel" }))

    expect(onCancel).toHaveBeenCalledTimes(1)
  })

  it("calls onConfirm when the confirm button is clicked", async () => {
    const user = userEvent.setup()
    const onConfirm = vi.fn()
    render(
      <ConfirmDialog
        title="t"
        description="d"
        confirmLabel="Revoke"
        onConfirm={onConfirm}
        onCancel={vi.fn()}
      />
    )

    await user.click(screen.getByRole("button", { name: "Revoke" }))

    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it("focuses the cancel button on open and returns focus to the trigger on close", async () => {
    function Harness() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button onClick={() => setOpen(true)}>Open</button>
          {open && (
            <ConfirmDialog
              title="t"
              description="d"
              onConfirm={() => setOpen(false)}
              onCancel={() => setOpen(false)}
            />
          )}
        </>
      )
    }
    const user = userEvent.setup()
    render(<Harness />)
    const trigger = screen.getByRole("button", { name: "Open" })
    trigger.focus()
    await user.click(trigger)

    await waitFor(() => expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus())

    await user.click(screen.getByRole("button", { name: "Cancel" }))

    await waitFor(() => expect(trigger).toHaveFocus())
  })
})
