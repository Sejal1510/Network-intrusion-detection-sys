import { useState } from "react"
import { CsvDropzone } from "@/components/upload/CsvDropzone"
import { BatchSummaryPanel } from "@/components/upload/BatchSummaryPanel"
import { ErrorState } from "@/components/common/ErrorState"
import { LoadingSkeleton } from "@/components/common/LoadingSkeleton"
import { useBatchPredict } from "@/hooks/useBatchPredict"
import { parseCsvFile, zipCsvWithResults, type ZippedRow } from "@/lib/csv"

export function BatchUploadPage() {
  const mutation = useBatchPredict()
  const [fileName, setFileName] = useState<string | null>(null)
  const [zippedRows, setZippedRows] = useState<ZippedRow[]>([])
  const [parseError, setParseError] = useState<string | null>(null)

  async function handleFile(file: File) {
    setFileName(file.name)
    setParseError(null)
    setZippedRows([])
    try {
      const [rows, response] = await Promise.all([
        parseCsvFile(file),
        mutation.mutateAsync({ file, explain: false }),
      ])
      setZippedRows(zipCsvWithResults(rows, response.results))
    } catch {
      // mutation.isError already surfaces the API failure; a client-side
      // parse failure is separate since it can happen even if the
      // upload itself succeeds server-side.
      setParseError("Could not parse the CSV file for the summary breakdown.")
    }
  }

  return (
    <div className="space-y-6">
      <h2 className="text-lg font-semibold text-[var(--text-primary)]">CSV Batch Upload</h2>
      <p className="text-sm text-[var(--text-secondary)]">
        Upload a CSV of raw connection records to score them all at once.
      </p>

      <CsvDropzone onFileSelected={handleFile} disabled={mutation.isPending} />
      {fileName && <p className="text-xs text-[var(--text-muted)]">Selected: {fileName}</p>}

      {mutation.isPending && <LoadingSkeleton rows={4} />}
      {mutation.isError && (
        <ErrorState
          message={mutation.error instanceof Error ? mutation.error.message : "Batch prediction failed."}
        />
      )}
      {parseError && <ErrorState message={parseError} />}

      {mutation.data && zippedRows.length > 0 && (
        <BatchSummaryPanel summary={mutation.data.summary} zippedRows={zippedRows} />
      )}
    </div>
  )
}
