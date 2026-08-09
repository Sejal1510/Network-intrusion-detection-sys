import { apiClient } from "@/api/client"
import type { Rule } from "@/api/types"

export function getRules(): Promise<Rule[]> {
  return apiClient.get<Rule[]>("/rules")
}
