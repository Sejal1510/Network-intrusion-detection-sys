import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"
import { LoginForm } from "./LoginForm"

describe("LoginForm", () => {
  it("submits the entered username and password", async () => {
    const user = userEvent.setup()
    const onSubmit = vi.fn()
    render(<LoginForm onSubmit={onSubmit} />)

    await user.type(screen.getByLabelText("Username"), "analyst1")
    await user.type(screen.getByLabelText("Password"), "hunter2")
    await user.click(screen.getByRole("button", { name: /sign in/i }))

    expect(onSubmit).toHaveBeenCalledWith("analyst1", "hunter2")
  })

  it("disables the submit button while submitting", () => {
    render(<LoginForm onSubmit={vi.fn()} submitting />)

    expect(screen.getByRole("button", { name: /signing in/i })).toBeDisabled()
  })

  it("shows an error message when provided", () => {
    render(<LoginForm onSubmit={vi.fn()} error="Invalid username or password." />)

    expect(screen.getByText("Invalid username or password.")).toBeInTheDocument()
  })
})
