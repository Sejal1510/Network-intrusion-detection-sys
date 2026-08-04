import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { ManualPredictForm } from "./ManualPredictForm"
import { MANUAL_PREDICT_FIELDS } from "./manualPredictFieldConfig"

describe("ManualPredictForm", () => {
  it("submits all 41 fields, reflecting edited categorical and numeric values", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<ManualPredictForm onSubmit={onSubmit} />)

    await user.selectOptions(screen.getByLabelText("Protocol"), "udp")
    const durationInput = screen.getByLabelText("Duration (s)")
    await user.clear(durationInput)
    await user.type(durationInput, "42")

    await user.click(screen.getByRole("button", { name: /predict/i }))

    expect(onSubmit).toHaveBeenCalledTimes(1)
    const [record, explain] = onSubmit.mock.calls[0]
    expect(Object.keys(record)).toHaveLength(MANUAL_PREDICT_FIELDS.length)
    expect(record.protocol_type).toBe("udp")
    expect(record.duration).toBe(42)
    expect(explain).toBe(true)
  })

  it("disables the submit button while submitting", () => {
    render(<ManualPredictForm onSubmit={vi.fn()} submitting />)

    expect(screen.getByRole("button", { name: /predicting/i })).toBeDisabled()
  })
})
