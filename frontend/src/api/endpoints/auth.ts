import { apiClient } from "@/api/client"
import type { CurrentUserResponse, LoginRequest, LoginResponse, WsTicketResponse } from "@/api/types"

export function login(payload: LoginRequest): Promise<LoginResponse> {
  return apiClient.post<LoginResponse>("/auth/login", payload)
}

export function logout(): Promise<void> {
  return apiClient.post<void>("/auth/logout")
}

export function getCurrentUser(): Promise<CurrentUserResponse> {
  return apiClient.get<CurrentUserResponse>("/auth/me")
}

/** Mints a short-lived ticket for /ws/live's handshake (see useLiveFeed). */
export function requestWsTicket(): Promise<WsTicketResponse> {
  return apiClient.post<WsTicketResponse>("/auth/ws-ticket")
}
