import { describe, expect, it } from "vitest"
import { ApiError } from "@/api/client"
import { shouldRetryQuery } from "./queryClient"

describe("shouldRetryQuery", () => {
  it("never retries a 4xx ApiError", () => {
    expect(shouldRetryQuery(0, new ApiError(401, "Not authenticated."))).toBe(false)
    expect(shouldRetryQuery(0, new ApiError(403, "Forbidden."))).toBe(false)
    expect(shouldRetryQuery(0, new ApiError(404, "Not found."))).toBe(false)
  })

  it("retries a 5xx ApiError up to the cap", () => {
    expect(shouldRetryQuery(0, new ApiError(503, "Unavailable."))).toBe(true)
    expect(shouldRetryQuery(1, new ApiError(503, "Unavailable."))).toBe(true)
    expect(shouldRetryQuery(2, new ApiError(503, "Unavailable."))).toBe(false)
  })

  it("retries a non-ApiError (e.g. a network failure) up to the cap", () => {
    expect(shouldRetryQuery(0, new TypeError("Failed to fetch"))).toBe(true)
    expect(shouldRetryQuery(2, new TypeError("Failed to fetch"))).toBe(false)
  })
})
