import { fireEvent, render, screen } from "@testing-library/react"
import { describe, expect, it, vi } from "vitest"
import { CsvDropzone } from "./CsvDropzone"

function makeFile(name: string, content: string): File {
  return new File([content], name, { type: "text/csv" })
}

describe("CsvDropzone", () => {
  it("accepts a valid .csv drop", () => {
    const onFileSelected = vi.fn()
    const onInvalidFile = vi.fn()
    render(<CsvDropzone onFileSelected={onFileSelected} onInvalidFile={onInvalidFile} />)

    const file = makeFile("records.csv", "a,b\n1,2")
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [file] } })

    expect(onFileSelected).toHaveBeenCalledWith(file)
    expect(onInvalidFile).not.toHaveBeenCalled()
  })

  it("rejects a non-.csv drop without ever calling onFileSelected", () => {
    const onFileSelected = vi.fn()
    const onInvalidFile = vi.fn()
    render(<CsvDropzone onFileSelected={onFileSelected} onInvalidFile={onInvalidFile} />)

    const file = makeFile("records.exe", "not a csv")
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [file] } })

    expect(onFileSelected).not.toHaveBeenCalled()
    expect(onInvalidFile).toHaveBeenCalledWith(expect.stringMatching(/isn't a \.csv file/))
  })

  it("rejects an empty-file drop", () => {
    const onFileSelected = vi.fn()
    const onInvalidFile = vi.fn()
    render(<CsvDropzone onFileSelected={onFileSelected} onInvalidFile={onInvalidFile} />)

    const file = makeFile("records.csv", "")
    fireEvent.drop(screen.getByRole("button"), { dataTransfer: { files: [file] } })

    expect(onFileSelected).not.toHaveBeenCalled()
    expect(onInvalidFile).toHaveBeenCalledWith(expect.stringMatching(/is empty/))
  })
})
