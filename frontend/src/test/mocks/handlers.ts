import { http, HttpResponse } from "msw"
import type { HealthResponse } from "@/api/types"

const API_BASE_URL = "http://localhost:8000"

export const handlers = [
  http.get(`${API_BASE_URL}/health`, () =>
    HttpResponse.json<HealthResponse>({
      status: "ok",
      model_loaded: true,
      database_configured: true,
    })
  ),
]
