import { useEffect, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";

import { dispatchAdminNotification } from "../api/adminNotifications";
import { listAdminEvents } from "../api/adminEvents";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { queryKeys } from "../lib/queryKeys";
import {
  type AdminNotificationCreateRequest,
  type AdminNotificationDispatchResponse,
  adminNotificationTypeSchema,
  notificationMethodSchema,
  type NotificationMethod,
} from "../types/adminNotifications";
import type { AdminEventListResponse } from "../types/adminEvents";

const notificationDispatchFormSchema = z
  .object({
    notification_type: adminNotificationTypeSchema,
    notification_method: notificationMethodSchema,
    body: z.string().trim().min(1, "Enter the message body."),
    title: z.string().trim().max(255).optional().or(z.literal("")),
    event_id: z.string().trim().max(36).optional().or(z.literal("")),
    reg_id: z.string().trim().max(18).optional().or(z.literal("")),
  })
  .superRefine((value, context) => {
    if (
      value.notification_type === "price_change" ||
      value.notification_type === "event_cancellation"
    ) {
      if (!value.event_id?.trim()) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["event_id"],
          message: "Select an event for this notification type.",
        });
      }

      if (value.reg_id?.trim()) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["reg_id"],
          message: "A registration ID is not allowed for this notification type.",
        });
      }
    }

    if (value.notification_type === "refund") {
      if (!value.reg_id?.trim()) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["reg_id"],
          message: "Enter a registration ID for refund notifications.",
        });
      }

      if (value.event_id?.trim()) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["event_id"],
          message: "An event ID is not allowed for refund notifications.",
        });
      }
    }
  });

type NotificationDispatchFormValues = z.infer<
  typeof notificationDispatchFormSchema
>;

export function AdminNotificationsPage() {
  const [dispatchResult, setDispatchResult] =
    useState<AdminNotificationDispatchResponse | null>(null);

  const eventsQuery = useQuery<AdminEventListResponse, ApiError>({
    queryKey: queryKeys.adminEvents.all,
    queryFn: ({ signal }) => listAdminEvents(signal),
  });

  const form = useForm<NotificationDispatchFormValues>({
    resolver: zodResolver(notificationDispatchFormSchema),
    defaultValues: {
      notification_type: "price_change",
      notification_method: "in_app",
      body: "",
      title: "",
      event_id: "",
      reg_id: "",
    },
  });

  const notificationType = form.watch("notification_type");
  const requiresEventTarget =
    notificationType === "price_change" || notificationType === "event_cancellation";

  useEffect(() => {
    if (
      requiresEventTarget &&
      !form.getValues("event_id") &&
      eventsQuery.data &&
      eventsQuery.data.events.length > 0
    ) {
      form.setValue("event_id", eventsQuery.data.events[0].id);
    }

    if (requiresEventTarget) {
      form.setValue("reg_id", "");
    } else {
      form.setValue("event_id", "");
    }
  }, [eventsQuery.data, form, requiresEventTarget]);

  const dispatchMutation = useMutation<
    AdminNotificationDispatchResponse,
    ApiError,
    AdminNotificationCreateRequest
  >({
    mutationFn: dispatchAdminNotification,
    onSuccess: (response) => {
      setDispatchResult(response);
    },
  });

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Notification dispatch"
          description="Send backend-supported price-change, event-cancellation, or refund notifications without inventing any notification history workflow."
        />
      </section>

      {dispatchResult ? (
        <section className="action-feedback" role="status">
          <p className="action-feedback__title">{dispatchResult.message}</p>
          <p className="action-feedback__meta">
            User notifications: {dispatchResult.user_notifications_created} | Staff notifications: {dispatchResult.staff_notifications_created} | Email recipients: {dispatchResult.email_recipients_count}
          </p>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Dispatch settings</h2>
            <p className="section-note">
              The target fields change with the notification type to match the backend validation rules exactly.
            </p>
          </div>
        </div>

        {form.formState.errors.root?.message ? (
          <div className="form-alert" role="alert">
            {form.formState.errors.root.message}
          </div>
        ) : null}

        <form
          className="auth-form"
          noValidate
          onSubmit={form.handleSubmit(async (values) => {
            form.clearErrors("root");
            setDispatchResult(null);

            const payload: AdminNotificationCreateRequest = {
              notification_type: values.notification_type,
              notification_method: values.notification_method,
              body: values.body.trim(),
              title: values.title?.trim() || undefined,
              event_id: requiresEventTarget ? values.event_id?.trim() || undefined : undefined,
              reg_id: requiresEventTarget ? undefined : values.reg_id?.trim() || undefined,
            };

            try {
              await dispatchMutation.mutateAsync(payload);
            } catch (error) {
              applyNotificationFormErrors(error, form.setError);
            }
          })}
        >
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label" htmlFor="admin-notification-type">
                Notification type
              </label>
              <select
                id="admin-notification-type"
                className="form-input"
                aria-invalid={form.formState.errors.notification_type ? "true" : "false"}
                {...form.register("notification_type")}
              >
                <option value="price_change">Price change</option>
                <option value="event_cancellation">Event cancellation</option>
                <option value="refund">Refund</option>
              </select>
              {form.formState.errors.notification_type ? (
                <p className="form-error">
                  {form.formState.errors.notification_type.message}
                </p>
              ) : null}
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="admin-notification-method">
                Delivery method
              </label>
              <select
                id="admin-notification-method"
                className="form-input"
                aria-invalid={form.formState.errors.notification_method ? "true" : "false"}
                {...form.register("notification_method")}
              >
                <option value="in_app">In-app</option>
                <option value="email">Email</option>
              </select>
              {form.formState.errors.notification_method ? (
                <p className="form-error">
                  {form.formState.errors.notification_method.message}
                </p>
              ) : null}
            </div>

            {requiresEventTarget ? (
              <div className="form-field">
                <label className="form-label" htmlFor="admin-notification-event-id">
                  Event
                </label>
                {eventsQuery.isPending ? (
                  <LoadingState label="Loading event options..." />
                ) : eventsQuery.isError ? (
                  <div className="form-alert" role="alert">
                    {eventsQuery.error.message}
                  </div>
                ) : eventsQuery.data.events.length === 0 ? (
                  <EmptyState
                    title="No events available"
                    description="Create an event first to dispatch price-change or cancellation notifications."
                  />
                ) : (
                  <>
                    <select
                      id="admin-notification-event-id"
                      className="form-input"
                      aria-invalid={form.formState.errors.event_id ? "true" : "false"}
                      {...form.register("event_id")}
                    >
                      {eventsQuery.data.events.map((event) => (
                        <option key={event.id} value={event.id}>
                          {event.title}
                        </option>
                      ))}
                    </select>
                    {form.formState.errors.event_id ? (
                      <p className="form-error">{form.formState.errors.event_id.message}</p>
                    ) : null}
                  </>
                )}
              </div>
            ) : (
              <div className="form-field">
                <label className="form-label" htmlFor="admin-notification-reg-id">
                  Registration ID
                </label>
                <input
                  id="admin-notification-reg-id"
                  type="text"
                  autoComplete="off"
                  className="form-input"
                  aria-invalid={form.formState.errors.reg_id ? "true" : "false"}
                  {...form.register("reg_id")}
                />
                {form.formState.errors.reg_id ? (
                  <p className="form-error">{form.formState.errors.reg_id.message}</p>
                ) : null}
              </div>
            )}

            <div className="form-field">
              <label className="form-label" htmlFor="admin-notification-title">
                Title
              </label>
              <input
                id="admin-notification-title"
                type="text"
                className="form-input"
                aria-invalid={form.formState.errors.title ? "true" : "false"}
                {...form.register("title")}
              />
              <p className="field-hint">
                Leave blank to let the backend apply its default notification title.
              </p>
              {form.formState.errors.title ? (
                <p className="form-error">{form.formState.errors.title.message}</p>
              ) : null}
            </div>
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="admin-notification-body">
              Message body
            </label>
            <textarea
              id="admin-notification-body"
              className="form-input form-textarea"
              rows={5}
              aria-invalid={form.formState.errors.body ? "true" : "false"}
              {...form.register("body")}
            />
            {form.formState.errors.body ? (
              <p className="form-error">{form.formState.errors.body.message}</p>
            ) : null}
          </div>

          <div className="panel__actions">
            <button
              type="submit"
              className="button-link button-link--primary"
              disabled={
                dispatchMutation.isPending ||
                (requiresEventTarget &&
                  (!!eventsQuery.isPending ||
                    !!eventsQuery.isError ||
                    (eventsQuery.data?.events.length ?? 0) === 0))
              }
            >
              {dispatchMutation.isPending ? "Sending..." : "Send notification"}
            </button>
          </div>
        </form>
      </section>
    </div>
  );
}

function applyNotificationFormErrors(
  error: unknown,
  setError: ReturnType<typeof useForm<NotificationDispatchFormValues>>["setError"],
) {
  const apiError =
    error instanceof ApiError
      ? error
      : new ApiError("Could not send the notification.", { code: "unknown" });

  if (!apiError.fieldErrors || Object.keys(apiError.fieldErrors).length === 0) {
    setError("root", { type: "server", message: apiError.message });
    return;
  }

  let handled = false;
  const fieldMap: Record<string, keyof NotificationDispatchFormValues> = {
    notification_type: "notification_type",
    notification_method: "notification_method",
    body: "body",
    title: "title",
    event_id: "event_id",
    reg_id: "reg_id",
  };

  for (const [field, messages] of Object.entries(apiError.fieldErrors)) {
    const message = messages[0];
    if (!message) {
      continue;
    }

    if (field === "form") {
      setError("root", { type: "server", message });
      handled = true;
      continue;
    }

    const mappedField = fieldMap[field];
    if (mappedField) {
      setError(mappedField, { type: "server", message });
      handled = true;
    }
  }

  if (!handled) {
    setError("root", { type: "server", message: apiError.message });
  }
}
