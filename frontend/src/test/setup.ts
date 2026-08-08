import "@testing-library/jest-dom/vitest"
import { afterAll, afterEach, beforeAll } from "vitest"
import { setSessionToken } from "@/api/client"
import { server } from "./mocks/server"

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => {
  server.resetHandlers()
  window.localStorage.clear()
  // client.ts's current-session-token is module-level state, outliving
  // any single test -- reset it so a login in one test can't leak an
  // Authorization header into an unrelated test.
  setSessionToken(null)
})
afterAll(() => server.close())
