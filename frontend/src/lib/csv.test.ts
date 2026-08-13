import { describe, expect, it } from "vitest"
import { validateCsvFile } from "./csv"

function makeFile(name: string, content: string): File {
  return new File([content], name, { type: "text/csv" })
}

describe("validateCsvFile", () => {
  it("accepts a non-empty .csv file", () => {
    expect(validateCsvFile(makeFile("records.csv", "a,b\n1,2"))).toBeNull()
  })

  it("accepts a .csv extension case-insensitively", () => {
    expect(validateCsvFile(makeFile("records.CSV", "a,b\n1,2"))).toBeNull()
  })

  it("rejects a non-.csv file", () => {
    expect(validateCsvFile(makeFile("records.txt", "a,b\n1,2"))).toMatch(/isn't a \.csv file/)
  })

  it("rejects an empty file", () => {
    expect(validateCsvFile(makeFile("records.csv", ""))).toMatch(/is empty/)
  })
})
