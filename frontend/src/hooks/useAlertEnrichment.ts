import { useQuery } from "@tanstack/react-query"
import { getAlertEnrichment } from "@/api/endpoints/history"

const POLL_INTERVAL_MS = 2000
const MAX_POLLS = 6 // ~12s -- comfortably covers two sequential 5s provider timeouts

/**
 * Threat-intel enrichment is dispatched asynchronously (see
 * docs/THREAT_INTEL.md) -- it may not exist yet the moment an alert row
 * is expanded. Polls briefly while empty, stops as soon as results land
 * (or after MAX_POLLS, for alerts with no routable indicators at all,
 * which will never produce a result -- see `nids.api.threat_intel.
 * extract_indicators`). `enabled` should be false until the row is
 * actually expanded, so collapsed rows never poll.
 */
export function useAlertEnrichment(alertId: string, enabled: boolean) {
  return useQuery({
    queryKey: ["alert-enrichment", alertId],
    queryFn: () => getAlertEnrichment(alertId),
    enabled,
    refetchInterval: (query) => {
      const items = query.state.data?.items
      if (items && items.length > 0) return false
      if (query.state.dataUpdateCount >= MAX_POLLS) return false
      return POLL_INTERVAL_MS
    },
  })
}
