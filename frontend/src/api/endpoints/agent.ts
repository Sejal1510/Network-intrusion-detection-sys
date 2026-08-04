import { apiClient } from "@/api/client"
import type { DeviceCredentialResponse, PairingTokenResponse } from "@/api/types"

export function requestPairingToken(): Promise<PairingTokenResponse> {
  return apiClient.post<PairingTokenResponse>("/agent/pair")
}

export function exchangePairingToken(
  pairingToken: string,
  deviceName: string
): Promise<DeviceCredentialResponse> {
  return apiClient.post<DeviceCredentialResponse>("/agent/pair/exchange", {
    pairing_token: pairingToken,
    device_name: deviceName,
  })
}
