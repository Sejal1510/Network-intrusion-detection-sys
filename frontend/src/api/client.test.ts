import { describe, expect, it } from "vitest"
import { http, HttpResponse } from "msw"
import { server } from "@/test/mocks/server"
import { ApiError, apiClient, apiWebSocketUrl } from "./client"

const BASE = "http://localhost:8000"

describe("apiClient.get", () => {
  it("returns parsed JSON on success", async () => {
    server.use(http.get(`${BASE}/ping`, () => HttpResponse.json({ ok: true })))

    const result = await apiClient.get<{ ok: boolean }>("/ping")

    expect(result).toEqual({ ok: true })
  })

  it("throws ApiError with the FastAPI detail message on failure", async () => {
    server.use(
      http.get(
        `${BASE}/broken`,
        () => HttpResponse.json({ detail: "No model is loaded." }, { status: 503 })
      )
    )

    await expect(apiClient.get("/broken")).rejects.toMatchObject(
      new ApiError(503, "No model is loaded.")
    )
  })
})

describe("apiClient.post", () => {
  it("sends a JSON body with Content-Type set", async () => {
    server.use(
      http.post(`${BASE}/echo`, async ({ request }) => {
        expect(request.headers.get("Content-Type")).toBe("application/json")
        return HttpResponse.json(await request.json())
      })
    )

    const result = await apiClient.post<{ a: number }>("/echo", { a: 1 })

    expect(result).toEqual({ a: 1 })
  })

  it("sends FormData without a JSON Content-Type header", async () => {
    server.use(
      http.post(`${BASE}/upload`, async ({ request }) => {
        expect(request.headers.get("Content-Type")).toMatch(/^multipart\/form-data/)
        return HttpResponse.json({ received: true })
      })
    )
    const formData = new FormData()
    formData.append("file", new Blob(["a,b\n1,2"]), "sample.csv")

    const result = await apiClient.post<{ received: boolean }>("/upload", formData)

    expect(result).toEqual({ received: true })
  })
})

describe("apiWebSocketUrl", () => {
  it("converts http to ws", () => {
    expect(apiWebSocketUrl("/ws/live?token=abc")).toBe("ws://localhost:8000/ws/live?token=abc")
  })
})
