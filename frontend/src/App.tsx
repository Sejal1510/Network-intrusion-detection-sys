import { lazy } from "react"
import { Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { RequireAuth } from "@/components/auth/RequireAuth"
import { LoginPage } from "@/routes/LoginPage"

// Lazy -- these are the routes nested under AppShell, loaded only once a
// user is authenticated and navigates to them. LoginPage stays a static
// import above: it's the first thing an unauthenticated visitor loads, so
// lazy-loading it would only add a chunk-fetch round trip for no benefit.
const OverviewPage = lazy(() => import("@/routes/OverviewPage").then((m) => ({ default: m.OverviewPage })))
const AlertsPage = lazy(() => import("@/routes/AlertsPage").then((m) => ({ default: m.AlertsPage })))
const HistoryPage = lazy(() => import("@/routes/HistoryPage").then((m) => ({ default: m.HistoryPage })))
const ManualPredictPage = lazy(() =>
  import("@/routes/ManualPredictPage").then((m) => ({ default: m.ManualPredictPage }))
)
const BatchUploadPage = lazy(() =>
  import("@/routes/BatchUploadPage").then((m) => ({ default: m.BatchUploadPage }))
)
const DevicesPage = lazy(() => import("@/routes/DevicesPage").then((m) => ({ default: m.DevicesPage })))
const AuditPage = lazy(() => import("@/routes/AuditPage").then((m) => ({ default: m.AuditPage })))
const MetricsPage = lazy(() => import("@/routes/MetricsPage").then((m) => ({ default: m.MetricsPage })))
const NotFoundPage = lazy(() => import("@/routes/NotFoundPage").then((m) => ({ default: m.NotFoundPage })))

function App() {
  return (
    <Routes>
      <Route path="login" element={<LoginPage />} />
      <Route element={<RequireAuth />}>
        <Route element={<AppShell />}>
          <Route index element={<OverviewPage />} />
          <Route path="alerts" element={<AlertsPage />} />
          <Route path="history" element={<HistoryPage />} />
          <Route path="predict" element={<ManualPredictPage />} />
          <Route path="upload" element={<BatchUploadPage />} />
          <Route path="audit" element={<AuditPage />} />
          <Route path="metrics" element={<MetricsPage />} />
          <Route element={<RequireAuth role="admin" />}>
            <Route path="devices" element={<DevicesPage />} />
          </Route>
          <Route path="*" element={<NotFoundPage />} />
        </Route>
      </Route>
    </Routes>
  )
}

export default App
