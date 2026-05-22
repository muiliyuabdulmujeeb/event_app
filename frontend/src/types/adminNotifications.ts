import { z } from "zod";

export const notificationMethodSchema = z.enum(["in_app", "email"]);
export const adminNotificationTypeSchema = z.enum([
  "price_change",
  "event_cancellation",
  "refund",
]);

export const adminNotificationCreateRequestSchema = z
  .object({
    notification_type: adminNotificationTypeSchema,
    notification_method: notificationMethodSchema.default("in_app"),
    body: z.string().trim().min(1),
    title: z.string().trim().min(1).max(255).optional(),
    event_id: z.string().trim().min(1).max(36).optional(),
    reg_id: z.string().trim().min(1).max(18).optional(),
  })
  .superRefine((value, context) => {
    if (
      value.notification_type === "price_change" ||
      value.notification_type === "event_cancellation"
    ) {
      if (!value.event_id) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["event_id"],
          message: "Event notifications require an event ID.",
        });
      }

      if (value.reg_id) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["reg_id"],
          message: "A registration ID is not allowed for this notification type.",
        });
      }
    }

    if (value.notification_type === "refund") {
      if (!value.reg_id) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["reg_id"],
          message: "Refund notifications require a registration ID.",
        });
      }

      if (value.event_id) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["event_id"],
          message: "An event ID is not allowed for refund notifications.",
        });
      }
    }
  });

export const adminNotificationDispatchResponseSchema = z.object({
  notification_type: adminNotificationTypeSchema,
  notification_method: notificationMethodSchema,
  user_notifications_created: z.number().int().nonnegative(),
  staff_notifications_created: z.number().int().nonnegative(),
  email_recipients_count: z.number().int().nonnegative(),
  message: z.string().min(1),
});

export type NotificationMethod = z.infer<typeof notificationMethodSchema>;
export type AdminNotificationType = z.infer<typeof adminNotificationTypeSchema>;
export type AdminNotificationCreateRequest = z.infer<
  typeof adminNotificationCreateRequestSchema
>;
export type AdminNotificationDispatchResponse = z.infer<
  typeof adminNotificationDispatchResponseSchema
>;
