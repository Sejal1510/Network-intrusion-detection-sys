import { useMutation } from "@tanstack/react-query"
import { predictOne } from "@/api/endpoints/predict"
import type { PredictRequest } from "@/api/types"

export function useManualPredict() {
  return useMutation({
    mutationFn: ({ record, explain }: { record: PredictRequest; explain: boolean }) =>
      predictOne(record, explain),
  })
}
