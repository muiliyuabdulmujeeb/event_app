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

export const cancellationReasonSchema = z.enum(["user_cancelled", "overflow_rule_changed"]);
export const paymentStatusSchema = z.enum(["pending", "successful", "failed"]);
export const refundRequestStatusSchema = z.enum(["requested", "approved", "rejected", "completed"]);
export const waitlistPromotionOfferStatusSchema = z.enum([
  "offered",
  "payment_initialized",
  "paid",
  "failed",
  "expired",
  "cancelled",
  "manual_review",
]);

export const registrationLookupCustomFieldValueSchema = z.object({
  label: z.string().min(1),
  value: z.string(),
});

export const registrationLookupRegistrationSchema = z.object({
  reg_id: z.string().min(1),
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  email: z.string().regex(emailRegex),
  state: registrationStateSchema,
  is_checked_in: z.boolean(),
  checked_in_at: z.string().datetime({ offset: true }).nullable(),
  registered_at: z.string().datetime({ offset: true }),
  is_batch: z.boolean(),
  was_waitlisted: z.boolean(),
  previous_waitlist_position: z.number().int().positive().nullable(),
  cancellation_reason: cancellationReasonSchema.nullable(),
  custom_field_values: z.array(registrationLookupCustomFieldValueSchema),
});

export const registrationLookupEventSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  event_date: z.string().datetime({ offset: true }),
  location: z.string().min(1),
  is_free: z.boolean(),
  state: z.enum(["draft", "published", "completed", "cancelled"]),
});

export const registrationLookupPaymentSchema = z.object({
  status: paymentStatusSchema,
  amount_paid: z.number().int().nonnegative(),
  currency: z.string().min(1),
  paid_at: z.string().datetime({ offset: true }).nullable(),
});

export const registrationLookupPromotionOfferSchema = z.object({
  public_token: z.string().min(1),
  status: waitlistPromotionOfferStatusSchema,
  offer_expires_at: z.string().datetime({ offset: true }),
  payment_action_url: z.string().url().nullable(),
});

export const registrationLookupRefundRequestSchema = z.object({
  id: z.string().min(1),
  status: refundRequestStatusSchema,
  requested_at: z.string().datetime({ offset: true }),
  processed_at: z.string().datetime({ offset: true }).nullable(),
});

export const userNotificationSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  body: z.string(),
  is_seen: z.boolean(),
  created_at: z.string().datetime({ offset: true }),
});

export const registrationLookupResponseSchema = z.object({
  registration: registrationLookupRegistrationSchema,
  event: registrationLookupEventSchema,
  payment: registrationLookupPaymentSchema.nullable(),
  promotion_offer: registrationLookupPromotionOfferSchema.nullable(),
  refund_request: registrationLookupRefundRequestSchema.nullable(),
  notifications: z.array(userNotificationSchema),
});

export const userNotificationSeenResponseSchema = z.object({
  id: z.string().min(1),
  is_seen: z.boolean(),
});

export const registrationCancellationRequestSchema = z.object({
  reason: z.string().trim().max(500).optional().nullable(),
});

export const registrationCancellationResponseSchema = z.object({
  reg_id: z.string().min(1),
  state: registrationStateSchema,
  was_waitlisted: z.boolean(),
  previous_waitlist_position: z.number().int().positive().nullable(),
  cancellation_reason: cancellationReasonSchema.nullable(),
  message: z.string().min(1),
});

export const refundRequestCreateRequestSchema = z.object({
  reason: z.string().trim().max(1000).optional().nullable(),
});

export const refundRequestCreateResponseSchema = z.object({
  refund_request_id: z.string().min(1),
  reg_id: z.string().min(1),
  status: refundRequestStatusSchema,
  requested_at: z.string().datetime({ offset: true }),
  message: z.string().min(1),
});

export const registrationPaymentInitializationResponseSchema = z.object({
  checkout_url: z.string().url(),
  payment_reference: z.string().min(1),
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
export type CancellationReason = z.infer<typeof cancellationReasonSchema>;
export type PaymentStatus = z.infer<typeof paymentStatusSchema>;
export type RefundRequestStatus = z.infer<typeof refundRequestStatusSchema>;
export type WaitlistPromotionOfferStatus = z.infer<typeof waitlistPromotionOfferStatusSchema>;
export type RegistrationLookupCustomFieldValue = z.infer<typeof registrationLookupCustomFieldValueSchema>;
export type RegistrationLookupRegistration = z.infer<typeof registrationLookupRegistrationSchema>;
export type RegistrationLookupEvent = z.infer<typeof registrationLookupEventSchema>;
export type RegistrationLookupPayment = z.infer<typeof registrationLookupPaymentSchema>;
export type RegistrationLookupPromotionOffer = z.infer<typeof registrationLookupPromotionOfferSchema>;
export type RegistrationLookupRefundRequest = z.infer<typeof registrationLookupRefundRequestSchema>;
export type UserNotification = z.infer<typeof userNotificationSchema>;
export type RegistrationLookupResponse = z.infer<typeof registrationLookupResponseSchema>;
export type UserNotificationSeenResponse = z.infer<typeof userNotificationSeenResponseSchema>;
export type RegistrationCancellationRequest = z.infer<typeof registrationCancellationRequestSchema>;
export type RegistrationCancellationResponse = z.infer<typeof registrationCancellationResponseSchema>;
export type RefundRequestCreateRequest = z.infer<typeof refundRequestCreateRequestSchema>;
export type RefundRequestCreateResponse = z.infer<typeof refundRequestCreateResponseSchema>;
export type RegistrationPaymentInitializationResponse = z.infer<
  typeof registrationPaymentInitializationResponseSchema
>;
