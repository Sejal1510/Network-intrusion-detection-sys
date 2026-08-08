import { useQuery } from "@tanstack/react-query"
import { listDevices, type DeviceListFilters } from "@/api/endpoints/devices"

export function useDevices(filters: DeviceListFilters) {
  return useQuery({
    queryKey: ["devices", filters],
    queryFn: () => listDevices(filters),
  })
}
