import { z } from "zod";
import { ApiContractError, apiFetch } from "@/lib/api";
import { recordSchema, uuidSchema } from "./views-schemas";

// One change of one field on several records of one module, through the
// existing `POST /api/records/batch-update` (candidates 1 and 5 of
// docs/specs/subtle-interactions.md). The server checks Write on the module
// and on each record, and each item's revision (the record's `updated_at`);
// every item answers alone. A write, so it never reports to the OpenView
// read latch.

/** The server takes at most 100 items in one request. */
export const RECORD_BATCH_LIMIT = 100;

const fieldErrorSchema = z
  .object({
    code: z.string(),
    field_id: uuidSchema.nullable(),
    message: z.string(),
  })
  .strict()
  .transform(({ field_id, ...error }) => ({ ...error, fieldId: field_id }));

const resultSchema = z.discriminatedUnion("status", [
  z
    .object({
      status: z.literal("updated"),
      record_id: uuidSchema,
      record: recordSchema,
    })
    .strict()
    .transform(({ record_id, ...result }) => ({
      ...result,
      recordId: record_id,
    })),
  z
    .object({ status: z.literal("stale"), record_id: uuidSchema })
    .strict()
    .transform(({ record_id, status }) => ({ status, recordId: record_id })),
  z
    .object({ status: z.literal("forbidden"), record_id: uuidSchema })
    .strict()
    .transform(({ record_id, status }) => ({ status, recordId: record_id })),
  z
    .object({
      status: z.literal("invalid"),
      record_id: uuidSchema,
      errors: z.array(fieldErrorSchema),
      // The server's default; OpenAPI marks it optional.
      truncated: z.boolean().optional(),
    })
    .strict()
    .transform(({ record_id, ...result }) => ({
      ...result,
      recordId: record_id,
    })),
]);

const batchResponseSchema = z
  .object({ results: z.array(resultSchema) })
  .strict();

export type RecordBatchResult = z.output<typeof resultSchema>;

export type RecordBatchItem = {
  recordId: string;
  /** The record's `updatedAt` that the person saw. */
  revision: string;
  fieldId: string;
  value: unknown;
};

/** Sends one field change per record; each result answers alone. */
export async function batchUpdateOpenViewRecords(input: {
  moduleId: string;
  items: readonly RecordBatchItem[];
}): Promise<RecordBatchResult[]> {
  if (input.items.length > RECORD_BATCH_LIMIT)
    throw new RangeError(
      `A batch holds at most ${RECORD_BATCH_LIMIT} records.`,
    );
  const response = await apiFetch(
    "/records/batch-update",
    batchResponseSchema,
    {
      method: "POST",
      cache: "no-store",
      body: JSON.stringify({
        module_id: uuidSchema.parse(input.moduleId),
        items: input.items.map((item) => ({
          record_id: uuidSchema.parse(item.recordId),
          revision: item.revision,
          field_id: uuidSchema.parse(item.fieldId),
          value: item.value ?? null,
        })),
      }),
    },
  );
  // Each record sent is answered once, by its id; any other answer is a
  // broken contract, never a refusal of a record (FX-PD4-N1).
  const sent = new Set(input.items.map((item) => item.recordId));
  const answered = new Set(response.results.map((result) => result.recordId));
  if (
    response.results.length !== input.items.length ||
    answered.size !== sent.size ||
    [...answered].some((recordId) => !sent.has(recordId))
  )
    throw new ApiContractError();
  return response.results;
}
