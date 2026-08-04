import { useMutation, useQueryClient } from "@tanstack/react-query"
import { acknowledgeAlert } from "@/api/endpoints/history"

export function useAcknowledgeAlert() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (alertId: string) => acknowledgeAlert(alertId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["alerts"] })
    },
  })
}
