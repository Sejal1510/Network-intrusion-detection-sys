import "@testing-library/jest-dom/vitest"
import { afterAll, afterEach, beforeAll } from "vitest"
import { setSessionToken, setUnauthorizedHandler } from "@/api/client"
import { server } from "./mocks/server"

beforeAll(() => server.listen({ onUnhandledRequest: "error" }))
afterEach(() => {
  server.resetHandlers()
  window.localStorage.clear()
  // client.ts's current-session-token and unauthorized-handler are
  // module-level state, outliving any single test -- reset both so a
  // login/handler registration in one test can't leak into an unrelated
  // test (an Authorization header, or a stale forced-logout callback).
  setSessionToken(null)
  setUnauthorizedHandler(null)
})
afterAll(() => server.close())
