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

export const batchParticipantRegistrationInputSchema = z.object({
  first_name: z.string().min(1).max(120),
  last_name: z.string().min(1).max(120),
  email: z.string().regex(emailRegex, "Please enter a valid email address."),
  custom_field_values: z.array(registrationCustomFieldValueInputSchema).default([]),
});

export const batchRegistrationRequestSchema = z.object({
  submitter_name: z.string().min(1).max(255),
  submitter_email: z.string().regex(emailRegex, "Please enter a valid email address."),
  acknowledge_duplicates: z.boolean().default(false),
  participants: z.array(batchParticipantRegistrationInputSchema).min(4),
});

export const batchRegistrationParticipantResponseSchema = z.object({
  reg_id: z.string().min(1),
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  email: z.string().regex(emailRegex),
});

export const batchRegistrationResponseSchema = z.object({
  batch_id: z.string().min(1),
  total_amount: z.number().int().nonnegative(),
  currency: z.string().min(1),
  participant_count: z.number().int().positive(),
  state: registrationStateSchema,
  payment_url: z.string().url().nullable(),
  participants: z.array(batchRegistrationParticipantResponseSchema),
  message: z.string().min(1),
});

export type RegistrationState = z.infer<typeof registrationStateSchema>;
export type RegistrationCustomFieldValueInput = z.infer<typeof registrationCustomFieldValueInputSchema>;
export type SingleRegistrationRequest = z.infer<typeof singleRegistrationRequestSchema>;
export type SingleRegistrationResponse = z.infer<typeof singleRegistrationResponseSchema>;
export type BatchParticipantRegistrationInput = z.infer<typeof batchParticipantRegistrationInputSchema>;
export type BatchRegistrationRequest = z.infer<typeof batchRegistrationRequestSchema>;
export type BatchRegistrationParticipantResponse = z.infer<typeof batchRegistrationParticipantResponseSchema>;
export type BatchRegistrationResponse = z.infer<typeof batchRegistrationResponseSchema>;
