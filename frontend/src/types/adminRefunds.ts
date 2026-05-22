import { z } from "zod";

import { notificationMethodSchema } from "./adminNotifications";

export const refundRequestStatusSchema = z.enum([
  "requested",
  "approved",
  "rejected",
  "completed",
]);

export const adminRefundRequestSummarySchema = z.object({
  refund_request_id: z.string().min(1),
  reg_id: z.string().min(1),
  status: refundRequestStatusSchema,
  requested_at: z.string().datetime({ offset: true }),
  processed_at: z.string().datetime({ offset: true }).nullable(),
});

export const adminRefundRequestListResponseSchema = z.object({
  items: z.array(adminRefundRequestSummarySchema),
  total: z.number().int().nonnegative(),
});

export const adminRefundRequestUpdateRequestSchema = z
  .object({
    status: refundRequestStatusSchema,
    notification_method: notificationMethodSchema,
    message_body: z.string().trim().min(1),
    title: z.string().trim().min(1).max(255).optional(),
    resolution_notes: z.string().trim().min(1).max(1000).optional(),
  })
  .superRefine((value, context) => {
    if (value.status === "requested") {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["status"],
        message: "Refund updates must move the request out of the requested state.",
      });
    }
  });

export const adminRefundRequestUpdateResponseSchema = z.object({
  refund_request_id: z.string().min(1),
  reg_id: z.string().min(1),
  status: refundRequestStatusSchema,
  processed_at: z.string().datetime({ offset: true }).nullable(),
  message: z.string().min(1),
});

export type RefundRequestStatus = z.infer<typeof refundRequestStatusSchema>;
export type AdminRefundRequestSummary = z.infer<
  typeof adminRefundRequestSummarySchema
>;
export type AdminRefundRequestListResponse = z.infer<
  typeof adminRefundRequestListResponseSchema
>;
export type AdminRefundRequestUpdateRequest = z.infer<
  typeof adminRefundRequestUpdateRequestSchema
>;
export type AdminRefundRequestUpdateResponse = z.infer<
  typeof adminRefundRequestUpdateResponseSchema
>;

export type AdminRefundListParams = {
  status?: RefundRequestStatus;
  eventId?: string;
  regId?: string;
};
