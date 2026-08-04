import { Route, Routes } from "react-router-dom"
import { AppShell } from "@/components/layout/AppShell"
import { OverviewPage } from "@/routes/OverviewPage"
import { AlertsPage } from "@/routes/AlertsPage"
import { HistoryPage } from "@/routes/HistoryPage"
import { ManualPredictPage } from "@/routes/ManualPredictPage"
import { BatchUploadPage } from "@/routes/BatchUploadPage"
import { NotFoundPage } from "@/routes/NotFoundPage"

function App() {
  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route index element={<OverviewPage />} />
        <Route path="alerts" element={<AlertsPage />} />
        <Route path="history" element={<HistoryPage />} />
        <Route path="predict" element={<ManualPredictPage />} />
        <Route path="upload" element={<BatchUploadPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}

export default App
