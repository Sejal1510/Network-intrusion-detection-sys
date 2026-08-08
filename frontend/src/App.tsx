import { Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { RequireAuth } from "@/components/auth/RequireAuth"
import { LoginPage } from "@/routes/LoginPage"
import { OverviewPage } from "@/routes/OverviewPage"
import { AlertsPage } from "@/routes/AlertsPage"
import { HistoryPage } from "@/routes/HistoryPage"
import { ManualPredictPage } from "@/routes/ManualPredictPage"
import { BatchUploadPage } from "@/routes/BatchUploadPage"
import { DevicesPage } from "@/routes/DevicesPage"
import { NotFoundPage } from "@/routes/NotFoundPage"

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
