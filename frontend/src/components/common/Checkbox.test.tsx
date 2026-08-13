import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { Checkbox } from "./Checkbox"

describe("Checkbox", () => {
  it("renders as a real checkbox, associated with its label", () => {
    render(<Checkbox id="explain" label="Explain this prediction (SHAP)" checked={false} onChange={vi.fn()} />)

    const checkbox = screen.getByRole("checkbox", { name: "Explain this prediction (SHAP)" })
    expect(checkbox).not.toBeChecked()
  })

  it("reflects a checked value", () => {
    render(<Checkbox id="explain" label="Explain this prediction (SHAP)" checked onChange={vi.fn()} />)

    expect(screen.getByRole("checkbox")).toBeChecked()
  })

  it("toggles via mouse click", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Checkbox id="explain" label="Explain this prediction (SHAP)" checked={false} onChange={onChange} />)

    await user.click(screen.getByRole("checkbox"))

    expect(onChange).toHaveBeenCalledTimes(1)
  })

  it("toggles via the keyboard (Space)", async () => {
    const user = userEvent.setup()
    const onChange = vi.fn()
    render(<Checkbox id="explain" label="Explain this prediction (SHAP)" checked={false} onChange={onChange} />)

    await user.tab()
    expect(screen.getByRole("checkbox")).toHaveFocus()
    await user.keyboard(" ")

    expect(onChange).toHaveBeenCalledTimes(1)
  })
})
