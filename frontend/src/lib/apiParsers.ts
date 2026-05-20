import { ZodType } from "zod";

import { createInvalidPayloadError } from "./apiError";

export function parseApiResponse<T>(schema: ZodType<T>, payload: unknown, context: string): T {
  const parsed = schema.safeParse(payload);
  if (!parsed.success) {
    throw createInvalidPayloadError(context);
  }
  return parsed.data;
}
