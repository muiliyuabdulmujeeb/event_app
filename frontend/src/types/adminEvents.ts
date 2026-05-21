import { z } from "zod";

import { eventFieldTypeSchema, eventStateSchema } from "./events";

export const overflowRuleSchema = z.enum(["hard_rejection", "waitlist"]);
export const notificationMethodSchema = z.enum(["in_app", "email"]);
export const priceChangeScopeSchema = z.enum([
  "new_registrations_only",
  "all_existing_confirmed",
]);

export const adminEventCustomFieldInputSchema = z.object({
  label: z.string().trim().min(1).max(255),
  field_type: eventFieldTypeSchema,
  is_required: z.boolean(),
  display_order: z.number().int().positive(),
});

export const adminEventCustomFieldResponseSchema = adminEventCustomFieldInputSchema.extend({
  id: z.string().min(1),
});

export const adminEventRegistrationCountsSchema = z.object({
  total_registrations: z.number().int().nonnegative(),
  pending_payment: z.number().int().nonnegative(),
  confirmed: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  cancelled: z.number().int().nonnegative(),
  refund_requested: z.number().int().nonnegative(),
  refunded: z.number().int().nonnegative(),
  waitlisted: z.number().int().nonnegative(),
});

export const adminEventSummarySchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string(),
  event_date: z.string().datetime({ offset: true }),
  location: z.string().min(1),
  prefix: z.string().min(2).max(5),
  price: z.number().int().nonnegative(),
  is_free: z.boolean(),
  capacity: z.number().int().positive().nullable(),
  overflow_rule: overflowRuleSchema,
  state: eventStateSchema,
  registration_count: z.number().int().nonnegative(),
  confirmed_count: z.number().int().nonnegative(),
  capacity_override_count: z.number().int().nonnegative(),
  slots_remaining: z.number().int().nonnegative().nullable(),
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
});

export const adminEventListResponseSchema = z.object({
  events: z.array(adminEventSummarySchema),
  total: z.number().int().nonnegative(),
});

export const adminEventDetailSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  description: z.string(),
  event_date: z.string().datetime({ offset: true }),
  location: z.string().min(1),
  prefix: z.string().min(2).max(5),
  price: z.number().int().nonnegative(),
  is_free: z.boolean(),
  capacity: z.number().int().positive().nullable(),
  overflow_rule: overflowRuleSchema,
  state: eventStateSchema,
  capacity_override_count: z.number().int().nonnegative(),
  slots_remaining: z.number().int().nonnegative().nullable(),
  custom_fields: z.array(adminEventCustomFieldResponseSchema),
  registration_counts: adminEventRegistrationCountsSchema,
  created_at: z.string().datetime({ offset: true }),
  updated_at: z.string().datetime({ offset: true }),
});

export const adminEventCreateRequestSchema = z.object({
  title: z.string().trim().min(1).max(255),
  description: z.string().trim().min(1),
  event_date: z.string().datetime({ offset: true }),
  location: z.string().trim().min(1).max(255),
  prefix: z.string().regex(/^[A-Z0-9]{2,5}$/),
  price: z.number().int().nonnegative(),
  capacity: z.number().int().positive().nullable(),
  overflow_rule: overflowRuleSchema,
  custom_fields: z.array(adminEventCustomFieldInputSchema),
});

export const adminEventUpdateRequestSchema = z
  .object({
    title: z.string().trim().min(1).max(255).optional(),
    description: z.string().trim().min(1).optional(),
    event_date: z.string().datetime({ offset: true }).optional(),
    location: z.string().trim().min(1).max(255).optional(),
    price: z.number().int().nonnegative().optional(),
    capacity: z.number().int().positive().nullable().optional(),
    custom_fields: z.array(adminEventCustomFieldInputSchema).optional(),
    price_change_scope: priceChangeScopeSchema.optional(),
    notification_method: notificationMethodSchema.optional(),
    notification_body: z.string().trim().min(1).optional(),
  })
  .superRefine((value, context) => {
    if (value.price_change_scope && value.price === undefined) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["price_change_scope"],
        message: "Price change scope requires a price update.",
      });
    }

    if (value.price_change_scope === "all_existing_confirmed") {
      if (!value.notification_method) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["notification_method"],
          message: "Notification method is required for existing confirmed registrations.",
        });
      }
      if (!value.notification_body) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["notification_body"],
          message: "Notification body is required for existing confirmed registrations.",
        });
      }
    }

    if (
      value.price_change_scope === "new_registrations_only" &&
      (value.notification_method || value.notification_body)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["price_change_scope"],
        message: "Notification settings are not allowed for new-registrations-only price changes.",
      });
    }

    if (
      !value.price_change_scope &&
      (value.notification_method || value.notification_body)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["price_change_scope"],
        message: "Notification settings require a selected price change scope.",
      });
    }
  });

export const adminEventStateUpdateRequestSchema = z
  .object({
    state: eventStateSchema,
    notification_method: notificationMethodSchema.optional(),
    notification_body: z.string().trim().min(1).optional(),
  })
  .superRefine((value, context) => {
    if (value.state === "cancelled" && !value.notification_body) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["notification_body"],
        message: "Cancellation requires a notification body.",
      });
    }

    if (
      value.state !== "cancelled" &&
      (value.notification_method || value.notification_body)
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["state"],
        message: "Notification settings are only allowed when cancelling an event.",
      });
    }
  });

export const adminEventOverflowRuleUpdateRequestSchema = z.object({
  overflow_rule: overflowRuleSchema,
  reason: z.string().trim().min(1),
});

export const adminEventOverflowRuleUpdateResponseSchema = z.object({
  event_id: z.string().min(1),
  overflow_rule: overflowRuleSchema,
  affected_waitlisted_registrations: z.number().int().nonnegative(),
  message: z.string().min(1),
});

export type OverflowRule = z.infer<typeof overflowRuleSchema>;
export type NotificationMethod = z.infer<typeof notificationMethodSchema>;
export type PriceChangeScope = z.infer<typeof priceChangeScopeSchema>;
export type AdminEventCustomFieldInput = z.infer<typeof adminEventCustomFieldInputSchema>;
export type AdminEventCustomFieldResponse = z.infer<typeof adminEventCustomFieldResponseSchema>;
export type AdminEventRegistrationCounts = z.infer<typeof adminEventRegistrationCountsSchema>;
export type AdminEventSummary = z.infer<typeof adminEventSummarySchema>;
export type AdminEventListResponse = z.infer<typeof adminEventListResponseSchema>;
export type AdminEventDetail = z.infer<typeof adminEventDetailSchema>;
export type AdminEventCreateRequest = z.infer<typeof adminEventCreateRequestSchema>;
export type AdminEventUpdateRequest = z.infer<typeof adminEventUpdateRequestSchema>;
export type AdminEventStateUpdateRequest = z.infer<typeof adminEventStateUpdateRequestSchema>;
export type AdminEventOverflowRuleUpdateRequest = z.infer<
  typeof adminEventOverflowRuleUpdateRequestSchema
>;
export type AdminEventOverflowRuleUpdateResponse = z.infer<
  typeof adminEventOverflowRuleUpdateResponseSchema
>;
