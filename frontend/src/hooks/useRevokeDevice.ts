import { useMutation, useQueryClient } from "@tanstack/react-query"
import { revokeDevice } from "@/api/endpoints/devices"

export function useRevokeDevice() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (deviceId: string) => revokeDevice(deviceId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["devices"] })
    },
  })
}
