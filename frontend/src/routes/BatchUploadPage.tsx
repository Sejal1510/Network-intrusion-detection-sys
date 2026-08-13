import { useState } from "react"
import { CsvDropzone } from "@/components/upload/CsvDropzone"
import { BatchSummaryPanel } from "@/components/upload/BatchSummaryPanel"
import { Card } from "@/components/common/Card"
import { TableSkeleton } from "@/components/common/TableSkeleton"
import { ErrorState } from "@/components/common/ErrorState"
import { useBatchPredict } from "@/hooks/useBatchPredict"
import { parseCsvFile, zipCsvWithResults, type ZippedRow } from "@/lib/csv"

/** Shaped like the real result panel (KPI row + chart + two tables) instead of a generic bar list. */
function BatchSummarySkeleton() {
  return (
    <div role="status" aria-label="Loading" className="space-y-6">
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {Array.from({ length: 4 }, (_, i) => (
          <Card key={i} interactive={false}>
            <div className="h-3 w-20 animate-pulse rounded bg-[var(--gridline)]" />
            <div className="mt-2 h-6 w-14 animate-pulse rounded bg-[var(--gridline)]" />
          </Card>
        ))}
      </div>
      <Card interactive={false}>
        <div className="h-[180px] animate-pulse rounded bg-[var(--gridline)]" />
      </Card>
      <TableSkeleton rows={4} columns={3} />
      <TableSkeleton rows={5} columns={5} />
    </div>
  )
}

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

      {mutation.isPending && <BatchSummarySkeleton />}
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
