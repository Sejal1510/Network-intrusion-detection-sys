import Papa from "papaparse"
import type { PredictResponse } from "@/api/types"

/**
 * Extension + non-empty only -- these are the two things drag-and-drop
 * currently lets through completely unchecked (the dropzone's native
 * `accept=".csv"` only ever filters the OS file picker, never a drop).
 * Deliberately doesn't try to enforce a byte-size ceiling: the server's
 * max upload size is a runtime deployment setting (--max-upload-size /
 * NIDS_MAX_UPLOAD_SIZE_BYTES), not a fixed constant safe to mirror here --
 * an oversized file is still caught by the existing 413 -> ErrorState path.
 */
export function validateCsvFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".csv")) {
    return `"${file.name}" isn't a .csv file.`
  }
  if (file.size === 0) {
    return `"${file.name}" is empty.`
  }
  return null
}

export function parseCsvFile(file: File): Promise<Record<string, string>[]> {
  return new Promise((resolve, reject) => {
    Papa.parse<Record<string, string>>(file, {
      header: true,
      skipEmptyLines: true,
      complete: (results) => resolve(results.data),
      error: (error: Error) => reject(error),
    })
  })
}

export interface ZippedRow {
  row: Record<string, string>
  result: PredictResponse
}

/**
 * Pairs row `i` of the uploaded CSV with `results[i]` from
 * /predict/batch. Safe only because that endpoint scores rows in
 * upload order (see docs/API.md and src/nids/api/app.py's
 * predict_batch_csv) -- PredictResponse itself carries no raw_record to
 * join on, unlike a persisted PredictionHistoryItem.
 */
export function zipCsvWithResults(rows: Record<string, string>[], results: PredictResponse[]): ZippedRow[] {
  return results.map((result, i) => ({ row: rows[i] ?? {}, result }))
}
