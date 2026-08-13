import { useState } from "react"
import { CategoricalField } from "@/components/forms/fields/CategoricalField"
import { NumericField } from "@/components/forms/fields/NumericField"
import { Button } from "@/components/common/Button"
import { Checkbox } from "@/components/common/Checkbox"
import { MANUAL_PREDICT_FIELDS, MANUAL_PREDICT_GROUPS } from "@/components/forms/manualPredictFieldConfig"
import type { PredictRequest } from "@/api/types"

function initialRecord(): PredictRequest {
  return Object.fromEntries(MANUAL_PREDICT_FIELDS.map((f) => [f.name, f.defaultValue]))
}

export function ManualPredictForm({
  onSubmit,
  submitting,
}: {
  onSubmit: (record: PredictRequest, explain: boolean) => void
  submitting?: boolean
}) {
  const [record, setRecord] = useState<PredictRequest>(initialRecord)
  const [explain, setExplain] = useState(true)

  function setField(name: string, value: string | number) {
    setRecord((prev) => ({ ...prev, [name]: value }))
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault()
        onSubmit(record, explain)
      }}
      className="space-y-6"
    >
      {MANUAL_PREDICT_GROUPS.map((group) => (
        <fieldset key={group} className="space-y-3">
          <legend className="text-sm font-medium text-[var(--text-primary)]">{group}</legend>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
            {MANUAL_PREDICT_FIELDS.filter((f) => f.group === group).map((field) => (
              <label key={field.name} htmlFor={field.name} className="block text-xs">
                <span className="mb-1 block text-[var(--text-secondary)]">{field.label}</span>
                {field.kind === "number" ? (
                  <NumericField
                    name={field.name}
                    value={record[field.name] as number}
                    onChange={(value) => setField(field.name, value)}
                  />
                ) : (
                  <CategoricalField
                    field={field}
                    value={record[field.name] as string}
                    onChange={(value) => setField(field.name, value)}
                  />
                )}
              </label>
            ))}
          </div>
        </fieldset>
      ))}

      <div className="flex items-center gap-4">
        <Checkbox
          id="explain-shap"
          checked={explain}
          onChange={(e) => setExplain(e.target.checked)}
          label="Explain this prediction (SHAP)"
        />
        <Button type="submit" disabled={submitting}>
          {submitting ? "Predicting…" : "Predict"}
        </Button>
      </div>
    </form>
  )
}
