import { apiClient } from "@/api/client"
import type { DeviceListItem, DeviceListResponse } from "@/api/types"

export interface DeviceListFilters {
  limit?: number
  offset?: number
}

function toQueryString(params: object): string {
  const search = new URLSearchParams()
  for (const [key, value] of Object.entries(params) as [string, string | number | undefined][]) {
    if (value !== undefined && value !== "") search.set(key, String(value))
  }
  const query = search.toString()
  return query ? `?${query}` : ""
}

export function listDevices(filters: DeviceListFilters): Promise<DeviceListResponse> {
  return apiClient.get<DeviceListResponse>(`/devices${toQueryString(filters)}`)
}

export function revokeDevice(deviceId: string): Promise<DeviceListItem> {
  return apiClient.post<DeviceListItem>(`/devices/${deviceId}/revoke`)
}
