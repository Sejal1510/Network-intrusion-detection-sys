import { StrictMode } from "react"
import { createRoot } from "react-dom/client"
import { BrowserRouter } from "react-router-dom"
import { QueryClientProvider } from "@tanstack/react-query"
import { createQueryClient } from "@/lib/queryClient"
import { DeviceAuthProvider } from "@/context/DeviceAuthProvider"
import { UserAuthProvider } from "@/context/UserAuthProvider"
import App from "./App.tsx"
import "./index.css"

const queryClient = createQueryClient()

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <UserAuthProvider>
        <DeviceAuthProvider>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </DeviceAuthProvider>
      </UserAuthProvider>
    </QueryClientProvider>
  </StrictMode>
)
