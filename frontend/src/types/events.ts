import { z } from "zod";

export const eventStateSchema = z.enum(["draft", "published", "completed", "cancelled"]);
export const eventFieldTypeSchema = z.enum(["text", "number", "date", "phone", "email"]);

export const publicEventCustomFieldSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  field_type: eventFieldTypeSchema,
  is_required: z.boolean(),
  display_order: z.number().int().positive(),
});

export const publicEventSummarySchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string(),
  event_date: z.string().datetime({ offset: true }),
  location: z.string().min(1),
  price: z.number().int().nonnegative(),
  is_free: z.boolean(),
  state: eventStateSchema,
  capacity: z.number().int().positive().nullable(),
});

export const publicEventListResponseSchema = z.object({
  events: z.array(publicEventSummarySchema),
  total: z.number().int().nonnegative(),
});

export const publicEventDetailSchema = publicEventSummarySchema.extend({
  custom_fields: z.array(publicEventCustomFieldSchema),
});

export type EventFieldType = z.infer<typeof eventFieldTypeSchema>;
export type PublicEventCustomField = z.infer<typeof publicEventCustomFieldSchema>;
export type PublicEventSummary = z.infer<typeof publicEventSummarySchema>;
export type PublicEventListResponse = z.infer<typeof publicEventListResponseSchema>;
export type PublicEventDetail = z.infer<typeof publicEventDetailSchema>;
