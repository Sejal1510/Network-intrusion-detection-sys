import type { FieldConfig } from "@/components/forms/manualPredictFieldConfig"

export function CategoricalField({
  field,
  value,
  onChange,
}: {
  field: FieldConfig
  value: string
  onChange: (value: string) => void
}) {
  if (field.kind === "select") {
    return (
      <select
        id={field.name}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1.5 text-sm"
      >
        {field.options?.map((option) => (
          <option key={option} value={option}>
            {option}
          </option>
        ))}
      </select>
    )
  }

  const listId = `${field.name}-options`
  return (
    <>
      <input
        id={field.name}
        list={listId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded border border-[var(--border-hairline)] bg-[var(--surface-card)] px-2 py-1.5 text-sm"
      />
      <datalist id={listId}>
        {field.options?.map((option) => (
          <option key={option} value={option} />
        ))}
      </datalist>
    </>
  )
}
