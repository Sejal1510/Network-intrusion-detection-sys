import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { DeviceAuthProvider } from "@/context/DeviceAuthProvider"
import App from "./App.tsx"
import "./index.css"

const queryClient = new QueryClient()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <DeviceAuthProvider>
        <BrowserRouter>
          <App />
        </BrowserRouter>
      </DeviceAuthProvider>
    </QueryClientProvider>
  </StrictMode>
)
