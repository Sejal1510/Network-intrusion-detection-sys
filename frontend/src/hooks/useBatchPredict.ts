import { useMutation } from "@tanstack/react-query"
import { predictBatch } from "@/api/endpoints/predict"

export function useBatchPredict() {
  return useMutation({
    mutationFn: ({ file, explain }: { file: File; explain: boolean }) => predictBatch(file, explain),
  })
}
