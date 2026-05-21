import { z } from "zod";

import { eventStateSchema } from "./events";
import { paymentStatusSchema, registrationStateSchema } from "./registrations";

export const staffRegistrationCustomFieldValueSchema = z.object({
  label: z.string().min(1),
  value: z.string(),
});

export const staffRegistrationEventSummarySchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  event_date: z.string().datetime({ offset: true }),
  location: z.string().min(1),
  is_free: z.boolean(),
  state: eventStateSchema,
  capacity_override_count: z.number().int().nonnegative(),
});

export const staffRegistrationPaymentSummarySchema = z.object({
  status: paymentStatusSchema,
  amount_paid: z.number().int().nonnegative(),
  currency: z.string().min(1),
  paid_at: z.string().datetime({ offset: true }).nullable(),
});

export const staffRegistrationResultSchema = z.object({
  reg_id: z.string().min(1),
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  email: z.string().email(),
  state: registrationStateSchema,
  is_checked_in: z.boolean(),
  checked_in_at: z.string().datetime({ offset: true }).nullable(),
  registered_at: z.string().datetime({ offset: true }),
  is_batch: z.boolean(),
  custom_field_values: z.array(staffRegistrationCustomFieldValueSchema),
  event: staffRegistrationEventSummarySchema,
  payment: staffRegistrationPaymentSummarySchema.nullable(),
});

export const staffRegistrationSearchResponseSchema = z.object({
  registrations: z.array(staffRegistrationResultSchema),
  total: z.number().int().nonnegative(),
});

export const staffCheckInResponseSchema = z.object({
  reg_id: z.string().min(1),
  state: registrationStateSchema,
  is_checked_in: z.boolean(),
  checked_in_at: z.string().datetime({ offset: true }).nullable(),
});

export const staffNotificationSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  body: z.string(),
  is_read: z.boolean(),
  created_at: z.string().datetime({ offset: true }),
});

export const staffNotificationListResponseSchema = z.object({
  notifications: z.array(staffNotificationSchema),
  total: z.number().int().nonnegative(),
});

export const staffNotificationReadResponseSchema = z.object({
  id: z.string().min(1),
  is_read: z.boolean(),
});

export type StaffRegistrationCustomFieldValue = z.infer<
  typeof staffRegistrationCustomFieldValueSchema
>;
export type StaffRegistrationEventSummary = z.infer<
  typeof staffRegistrationEventSummarySchema
>;
export type StaffRegistrationPaymentSummary = z.infer<
  typeof staffRegistrationPaymentSummarySchema
>;
export type StaffRegistrationResult = z.infer<typeof staffRegistrationResultSchema>;
export type StaffRegistrationSearchResponse = z.infer<
  typeof staffRegistrationSearchResponseSchema
>;
export type StaffCheckInResponse = z.infer<typeof staffCheckInResponseSchema>;
export type StaffNotification = z.infer<typeof staffNotificationSchema>;
export type StaffNotificationListResponse = z.infer<
  typeof staffNotificationListResponseSchema
>;
export type StaffNotificationReadResponse = z.infer<
  typeof staffNotificationReadResponseSchema
>;
