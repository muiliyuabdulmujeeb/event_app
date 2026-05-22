import { z } from "zod";

export const analyticsRegistrationStateSchema = z.enum([
  "pending_payment",
  "confirmed",
  "failed",
  "cancelled",
  "waitlisted",
]);

export const analyticsPaymentStatusSchema = z.enum([
  "pending",
  "successful",
  "failed",
]);

export const analyticsRefundStatusSchema = z.enum([
  "requested",
  "approved",
  "rejected",
  "completed",
]);

export const analyticsCancellationReasonSchema = z.enum([
  "user_cancelled",
  "overflow_rule_changed",
]);

export const analyticsPaymentGatewaySchema = z.enum([
  "paystack",
  "squad",
  "mock",
]);

export const analyticsDateSchema = z.string().regex(/^\d{4}-\d{2}-\d{2}$/);
export const analyticsDownloadFormatSchema = z.enum(["csv", "pdf"]);

export const adminAnalyticsRegistrationSortFields = [
  "registered_at",
  "reg_id",
  "first_name",
  "last_name",
  "email",
  "registration_state",
  "is_checked_in",
  "checked_in_at",
  "is_batch",
  "event_title",
  "event_date",
  "amount_paid",
  "payment_status",
  "paid_at",
] as const;

export const adminAnalyticsSortOrderSchema = z.enum(["asc", "desc"]);
export const adminAnalyticsRegistrationSortFieldSchema = z.enum(
  adminAnalyticsRegistrationSortFields,
);

export const adminAnalyticsRegistrationCustomFieldSchema = z.object({
  label: z.string().min(1),
  value: z.string(),
});

export const adminAnalyticsRegistrationEventSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
  event_date: z.string().datetime({ offset: true }),
  location: z.string().min(1),
  is_free: z.boolean(),
});

export const adminAnalyticsRegistrationPaymentSchema = z.object({
  amount_paid: z.number().int().nonnegative(),
  currency: z.string().min(1),
  payment_gateway: analyticsPaymentGatewaySchema.nullable(),
  payment_reference: z.string().nullable(),
  payment_status: analyticsPaymentStatusSchema.nullable(),
  paid_at: z.string().datetime({ offset: true }).nullable(),
});

export const adminAnalyticsRegistrationRowSchema = z.object({
  reg_id: z.string().min(1),
  first_name: z.string().min(1),
  last_name: z.string().min(1),
  email: z.string().email(),
  registration_state: analyticsRegistrationStateSchema,
  refund_status: analyticsRefundStatusSchema.nullable(),
  cancellation_reason: analyticsCancellationReasonSchema.nullable(),
  was_waitlisted: z.boolean(),
  previous_waitlist_position: z.number().int().positive().nullable(),
  is_checked_in: z.boolean(),
  checked_in_at: z.string().datetime({ offset: true }).nullable(),
  registered_at: z.string().datetime({ offset: true }),
  is_batch: z.boolean(),
  batch_submitter_name: z.string().nullable(),
  batch_submitter_email: z.string().nullable(),
  used_exception_offer: z.boolean(),
  payment_waived: z.boolean(),
  capacity_override_applied: z.boolean(),
  event: adminAnalyticsRegistrationEventSchema,
  payment: adminAnalyticsRegistrationPaymentSchema.nullable(),
  custom_fields: z.array(adminAnalyticsRegistrationCustomFieldSchema),
});

export const adminAnalyticsRegistrationsResponseSchema = z.object({
  page: z.number().int().positive(),
  page_size: z.number().int().positive(),
  total: z.number().int().nonnegative(),
  sort_by: z.string().min(1),
  sort_order: adminAnalyticsSortOrderSchema,
  registrations: z.array(adminAnalyticsRegistrationRowSchema),
});

export const adminAnalyticsEventReferenceSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
});

export const adminAnalyticsDateRangeSchema = z.object({
  from: analyticsDateSchema.nullable(),
  to: analyticsDateSchema.nullable(),
});

export const adminAnalyticsRegistrationSummarySchema = z.object({
  total_registrations: z.number().int().nonnegative(),
  confirmed: z.number().int().nonnegative(),
  cancelled: z.number().int().nonnegative(),
  waitlisted: z.number().int().nonnegative(),
  refunded: z.number().int().nonnegative(),
  failed: z.number().int().nonnegative(),
  checked_in_count: z.number().int().nonnegative(),
  check_in_rate: z.string().min(1),
});

export const adminAnalyticsRevenueByEventSchema = z.object({
  event_id: z.string().min(1),
  title: z.string().min(1),
  gross_revenue: z.number().int().nonnegative(),
});

export const adminAnalyticsRevenueSchema = z.object({
  gross_revenue: z.number().int().nonnegative(),
  net_revenue: z.number().int().nonnegative(),
  total_refunded: z.number().int().nonnegative(),
  average_ticket_price: z.number().int().nonnegative(),
  currency: z.string().min(1),
  revenue_by_event: z.array(adminAnalyticsRevenueByEventSchema),
});

export const adminAnalyticsTrendPointSchema = z.object({
  date: analyticsDateSchema,
  count: z.number().int().nonnegative(),
  cumulative: z.number().int().nonnegative(),
});

export const adminAnalyticsRegistrationTrendsSchema = z.object({
  peak_registration_day: analyticsDateSchema.nullable(),
  daily: z.array(adminAnalyticsTrendPointSchema),
});

export const adminAnalyticsBatchVsSingleSchema = z.object({
  single_registration_count: z.number().int().nonnegative(),
  batch_registration_count: z.number().int().nonnegative(),
  batch_submission_count: z.number().int().nonnegative(),
  average_batch_size: z.number().nonnegative(),
});

export const adminAnalyticsCapacitySchema = z.object({
  capacity: z.number().int().nonnegative(),
  slots_filled: z.number().int().nonnegative(),
  slots_remaining: z.number().int().nonnegative(),
  waitlist_length: z.number().int().nonnegative(),
  fill_rate: z.string().min(1),
  capacity_override_count: z.number().int().nonnegative(),
});

export const adminAnalyticsSummaryResponseSchema = z.object({
  events: z.array(adminAnalyticsEventReferenceSchema),
  date_range: adminAnalyticsDateRangeSchema,
  registration_summary: adminAnalyticsRegistrationSummarySchema,
  revenue: adminAnalyticsRevenueSchema,
  registration_trends: adminAnalyticsRegistrationTrendsSchema,
  batch_vs_single: adminAnalyticsBatchVsSingleSchema,
  capacity: adminAnalyticsCapacitySchema.optional(),
});

export type AnalyticsRegistrationState = z.infer<
  typeof analyticsRegistrationStateSchema
>;
export type AnalyticsPaymentStatus = z.infer<
  typeof analyticsPaymentStatusSchema
>;
export type AnalyticsDownloadFormat = z.infer<
  typeof analyticsDownloadFormatSchema
>;
export type AnalyticsRefundStatus = z.infer<
  typeof analyticsRefundStatusSchema
>;
export type AnalyticsCancellationReason = z.infer<
  typeof analyticsCancellationReasonSchema
>;
export type AnalyticsPaymentGateway = z.infer<
  typeof analyticsPaymentGatewaySchema
>;
export type AdminAnalyticsRegistrationSortField = z.infer<
  typeof adminAnalyticsRegistrationSortFieldSchema
>;
export type AdminAnalyticsSortOrder = z.infer<
  typeof adminAnalyticsSortOrderSchema
>;
export type AdminAnalyticsRegistrationSortBy =
  | AdminAnalyticsRegistrationSortField
  | `custom_field:${string}`;
export type AdminAnalyticsRegistrationCustomField = z.infer<
  typeof adminAnalyticsRegistrationCustomFieldSchema
>;
export type AdminAnalyticsRegistrationEvent = z.infer<
  typeof adminAnalyticsRegistrationEventSchema
>;
export type AdminAnalyticsRegistrationPayment = z.infer<
  typeof adminAnalyticsRegistrationPaymentSchema
>;
export type AdminAnalyticsRegistrationRow = z.infer<
  typeof adminAnalyticsRegistrationRowSchema
>;
export type AdminAnalyticsRegistrationsResponse = z.infer<
  typeof adminAnalyticsRegistrationsResponseSchema
>;
export type AdminAnalyticsEventReference = z.infer<
  typeof adminAnalyticsEventReferenceSchema
>;
export type AdminAnalyticsDateRange = z.infer<
  typeof adminAnalyticsDateRangeSchema
>;
export type AdminAnalyticsRegistrationSummary = z.infer<
  typeof adminAnalyticsRegistrationSummarySchema
>;
export type AdminAnalyticsRevenueByEvent = z.infer<
  typeof adminAnalyticsRevenueByEventSchema
>;
export type AdminAnalyticsRevenue = z.infer<
  typeof adminAnalyticsRevenueSchema
>;
export type AdminAnalyticsTrendPoint = z.infer<
  typeof adminAnalyticsTrendPointSchema
>;
export type AdminAnalyticsRegistrationTrends = z.infer<
  typeof adminAnalyticsRegistrationTrendsSchema
>;
export type AdminAnalyticsBatchVsSingle = z.infer<
  typeof adminAnalyticsBatchVsSingleSchema
>;
export type AdminAnalyticsCapacity = z.infer<
  typeof adminAnalyticsCapacitySchema
>;
export type AdminAnalyticsSummaryResponse = z.infer<
  typeof adminAnalyticsSummaryResponseSchema
>;

export type AdminAnalyticsSummaryParams = {
  event_ids?: string[];
  date_from?: string;
  date_to?: string;
};

export type AdminAnalyticsRegistrationsParams = {
  event_ids?: string[];
  date_from?: string;
  date_to?: string;
  state?: AnalyticsRegistrationState;
  is_checked_in?: boolean;
  email?: string;
  first_name?: string;
  last_name?: string;
  is_batch?: boolean;
  payment_status?: AnalyticsPaymentStatus;
  paid_from?: string;
  paid_to?: string;
  amount_min?: number;
  amount_max?: number;
  custom_field?: string[];
  page?: number;
  page_size?: number;
  sort_by?: AdminAnalyticsRegistrationSortBy;
  sort_order?: AdminAnalyticsSortOrder;
};

export type AdminAnalyticsDownloadParams = Omit<
  AdminAnalyticsRegistrationsParams,
  "page" | "page_size"
> & {
  format: AnalyticsDownloadFormat;
};
