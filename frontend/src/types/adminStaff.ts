import { z } from "zod";

export const staffRoleSchema = z.enum(["admin", "staff"]);
export const staffAccessModeSchema = z.enum(["all_events", "selected_events"]);

export const adminStaffSelectedEventSchema = z.object({
  id: z.string().min(1),
  title: z.string().min(1),
});

export const adminStaffAccountSummarySchema = z.object({
  id: z.string().min(1),
  email: z.string().email(),
  role: staffRoleSchema,
  is_active: z.boolean(),
  created_at: z.string().datetime({ offset: true }),
});

export const adminStaffAccountDetailSchema = adminStaffAccountSummarySchema.extend({
  access_mode: staffAccessModeSchema,
  selected_events: z.array(adminStaffSelectedEventSchema),
});

export const adminStaffAccountUpdateRequestSchema = z
  .object({
    email: z.string().trim().email().optional(),
    role: staffRoleSchema.optional(),
    is_active: z.boolean().optional(),
  })
  .superRefine((value, context) => {
    if (
      value.email === undefined &&
      value.role === undefined &&
      value.is_active === undefined
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["email"],
        message: "At least one field must be provided.",
      });
    }
  });

export const adminStaffAccessModeUpdateRequestSchema = z.object({
  mode: staffAccessModeSchema,
});

export const adminStaffEventAccessAddRequestSchema = z.object({
  event_id: z.string().trim().min(1).max(36),
});

export const adminStaffAccessConfigResponseSchema = z.object({
  staff_id: z.string().min(1),
  access_mode: staffAccessModeSchema,
  selected_events: z.array(adminStaffSelectedEventSchema),
});

export type StaffRole = z.infer<typeof staffRoleSchema>;
export type StaffAccessMode = z.infer<typeof staffAccessModeSchema>;
export type AdminStaffSelectedEvent = z.infer<typeof adminStaffSelectedEventSchema>;
export type AdminStaffAccountSummary = z.infer<typeof adminStaffAccountSummarySchema>;
export type AdminStaffAccountDetail = z.infer<typeof adminStaffAccountDetailSchema>;
export type AdminStaffAccountUpdateRequest = z.infer<typeof adminStaffAccountUpdateRequestSchema>;
export type AdminStaffAccessModeUpdateRequest = z.infer<
  typeof adminStaffAccessModeUpdateRequestSchema
>;
export type AdminStaffEventAccessAddRequest = z.infer<
  typeof adminStaffEventAccessAddRequestSchema
>;
export type AdminStaffAccessConfigResponse = z.infer<
  typeof adminStaffAccessConfigResponseSchema
>;
