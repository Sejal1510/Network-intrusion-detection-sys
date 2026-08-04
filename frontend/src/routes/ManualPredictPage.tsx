import { ManualPredictForm } from "@/components/forms/ManualPredictForm"
import { PredictionResultCard } from "@/components/forms/PredictionResultCard"
import { ErrorState } from "@/components/common/ErrorState"
import { useManualPredict } from "@/hooks/useManualPredict"

export function ManualPredictPage() {
  const mutation = useManualPredict()

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">Manual Predict</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Submit a single raw connection record and see how the served model scores it.
      </p>

      <ManualPredictForm
        submitting={mutation.isPending}
        onSubmit={(record, explain) => mutation.mutate({ record, explain })}
      />

      {mutation.isError && (
        <ErrorState message={mutation.error instanceof Error ? mutation.error.message : "Prediction failed."} />
      )}
      {mutation.data && <PredictionResultCard result={mutation.data} />}
    </div>
  )
}
