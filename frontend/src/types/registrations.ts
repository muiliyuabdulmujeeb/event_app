import { z } from "zod";

const emailRegex = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;

export const registrationStateSchema = z.enum([
  "pending_payment",
  "confirmed",
  "waitlisted",
  "failed",
  "cancelled",
]);

export const registrationCustomFieldValueInputSchema = z.object({
  field_definition_id: z.string().min(1).max(36),
  value: z.string().min(1),
});

export const singleRegistrationRequestSchema = z.object({
  first_name: z.string().min(1).max(120),
  last_name: z.string().min(1).max(120),
  email: z.string().regex(emailRegex, "Please enter a valid email address."),
  acknowledge_duplicate: z.boolean().default(false),
  custom_field_values: z.array(registrationCustomFieldValueInputSchema).default([]),
});

export const singleRegistrationResponseSchema = z.object({
  reg_id: z.string().min(1),
  state: registrationStateSchema,
  is_free: z.boolean(),
  payment_url: z.string().url().nullable(),
  message: z.string().min(1),
});

export type RegistrationState = z.infer<typeof registrationStateSchema>;
export type RegistrationCustomFieldValueInput = z.infer<typeof registrationCustomFieldValueInputSchema>;
export type SingleRegistrationRequest = z.infer<typeof singleRegistrationRequestSchema>;
export type SingleRegistrationResponse = z.infer<typeof singleRegistrationResponseSchema>;
