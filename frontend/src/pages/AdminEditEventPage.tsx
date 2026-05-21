import { useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";

import {
  getAdminEventDetail,
  updateAdminEvent,
  updateAdminEventOverflowRule,
  updateAdminEventState,
} from "../api/adminEvents";
import { AdminEventForm } from "../components/AdminEventForm";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type {
  AdminEventDetail,
  AdminEventOverflowRuleUpdateRequest,
  AdminEventOverflowRuleUpdateResponse,
  AdminEventStateUpdateRequest,
  NotificationMethod,
  OverflowRule,
} from "../types/adminEvents";
import { notificationMethodSchema, overflowRuleSchema } from "../types/adminEvents";
import type { EventState } from "../types/events";

export function AdminEditEventPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const queryClient = useQueryClient();
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);

  if (!eventId) {
    return (
      <ErrorState
        title="Event unavailable"
        message="The admin event identifier is missing from the current route."
      />
    );
  }

  const eventQuery = useQuery<AdminEventDetail, ApiError>({
    queryKey: queryKeys.adminEvents.detail(eventId),
    queryFn: ({ signal }) => getAdminEventDetail(eventId, signal),
  });

  const updateMutation = useMutation<AdminEventDetail, ApiError, Parameters<typeof updateAdminEvent>[1]>({
    mutationFn: (payload) => updateAdminEvent(eventId, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.adminEvents.detail(eventId), response);
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminEvents.all });
      setUpdateMessage("Event details were updated.");
    },
  });

  const stateMutation = useMutation<AdminEventDetail, ApiError, AdminEventStateUpdateRequest>({
    mutationFn: (payload) => updateAdminEventState(eventId, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.adminEvents.detail(eventId), response);
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminEvents.all });
      setUpdateMessage(`Event state updated to ${formatEventState(response.state).toLowerCase()}.`);
    },
  });

  const overflowMutation = useMutation<
    AdminEventOverflowRuleUpdateResponse,
    ApiError,
    AdminEventOverflowRuleUpdateRequest
  >({
    mutationFn: (payload) => updateAdminEventOverflowRule(eventId, payload),
    onSuccess: (response) => {
      queryClient.setQueryData<AdminEventDetail | undefined>(
        queryKeys.adminEvents.detail(eventId),
        (current) =>
          current
            ? {
                ...current,
                overflow_rule: response.overflow_rule,
              }
            : current,
      );
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminEvents.detail(eventId) });
      void queryClient.invalidateQueries({ queryKey: queryKeys.adminEvents.all });
      setUpdateMessage(response.message);
    },
  });

  if (eventQuery.isPending) {
    return <LoadingState label="Loading event editor..." />;
  }

  if (eventQuery.isError) {
    return (
      <ErrorState
        title={eventQuery.error.code === "notFound" ? "Event not found" : "Could not load this event"}
        message={eventQuery.error.message}
      />
    );
  }

  const event = eventQuery.data;

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title={`Edit ${event.title}`}
          description="Update the event record, manage eligible state transitions, and adjust overflow behavior through the dedicated backend workflows."
        />
        <div className="panel__actions">
          <Link to="/admin/events" className="button-link">
            Back to events
          </Link>
        </div>
      </section>

      {updateMessage ? (
        <div className="action-feedback" role="status">
          <p className="action-feedback__title">{updateMessage}</p>
        </div>
      ) : null}

      <section className="metric-grid">
        <MetricCard label="State" value={formatEventState(event.state)} />
        <MetricCard label="Pricing" value={event.is_free ? "Free" : formatPrice(event.price)} />
        <MetricCard label="Capacity" value={event.capacity ?? "Unlimited"} />
        <MetricCard label="Slots remaining" value={event.slots_remaining ?? "Unlimited"} />
        <MetricCard label="Confirmed registrations" value={event.registration_counts.confirmed} />
        <MetricCard label="Capacity overrides" value={event.capacity_override_count} />
      </section>

      <section className="panel">
        <div className="event-detail-grid">
          <article className="detail-card">
            <h2 className="detail-card__title">Event metadata</h2>
            <dl className="detail-list">
              <div>
                <dt>Prefix</dt>
                <dd>{event.prefix}</dd>
              </div>
              <div>
                <dt>Event date</dt>
                <dd>{formatDateTime(event.event_date)}</dd>
              </div>
              <div>
                <dt>Created at</dt>
                <dd>{formatDateTime(event.created_at)}</dd>
              </div>
              <div>
                <dt>Last updated</dt>
                <dd>{formatDateTime(event.updated_at)}</dd>
              </div>
            </dl>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Registration counts</h2>
            <dl className="detail-list">
              <div>
                <dt>Total registrations</dt>
                <dd>{event.registration_counts.total_registrations}</dd>
              </div>
              <div>
                <dt>Pending payment</dt>
                <dd>{event.registration_counts.pending_payment}</dd>
              </div>
              <div>
                <dt>Waitlisted</dt>
                <dd>{event.registration_counts.waitlisted}</dd>
              </div>
              <div>
                <dt>Refund requested</dt>
                <dd>{event.registration_counts.refund_requested}</dd>
              </div>
            </dl>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Event details</h2>
            <p className="section-note">
              Generic event updates use the standard admin event update endpoint. Overflow rules remain a separate action.
            </p>
          </div>
        </div>

        <AdminEventForm
          backHref="/admin/events"
          event={event}
          isSubmitting={updateMutation.isPending}
          mode="edit"
          onSubmit={async (payload) => {
            await updateMutation.mutateAsync(payload as Parameters<typeof updateAdminEvent>[1]);
          }}
          submitLabel="Save changes"
        />
      </section>

      <section className="event-detail-grid">
        <StateTransitionPanel
          event={event}
          isPending={stateMutation.isPending}
          key={`state-${event.updated_at}`}
          onSubmit={async (payload) => {
            await stateMutation.mutateAsync(payload);
          }}
        />
        <OverflowRulePanel
          currentRule={event.overflow_rule}
          isPending={overflowMutation.isPending}
          key={`overflow-${event.updated_at}`}
          onSubmit={async (payload) => {
            await overflowMutation.mutateAsync(payload);
          }}
        />
      </section>
    </div>
  );
}

function StateTransitionPanel({
  event,
  isPending,
  onSubmit,
}: {
  event: AdminEventDetail;
  isPending: boolean;
  onSubmit: (payload: AdminEventStateUpdateRequest) => Promise<void>;
}) {
  const allowedStates = useMemo(() => getAllowedNextStates(event.state), [event.state]);
  const schema = useMemo(() => buildStateTransitionSchema(allowedStates), [allowedStates]);
  const form = useForm<StateTransitionValues>({
    resolver: zodResolver(schema),
    defaultValues: {
      state: allowedStates[0] ?? event.state,
      notificationMethod: "",
      notificationBody: "",
    },
  });

  const selectedState = form.watch("state");

  if (allowedStates.length === 0) {
    return (
      <article className="detail-card">
        <h2 className="detail-card__title">State transitions</h2>
        <p className="detail-card__text">
          No further admin state transitions are available from the current {formatEventState(event.state).toLowerCase()} state.
        </p>
      </article>
    );
  }

  return (
    <article className="detail-card">
      <div className="section-header">
        <div>
          <h2 className="detail-card__title">State transitions</h2>
          <p className="section-note">
            Only backend-supported transitions are available here.
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

          try {
            await onSubmit({
              state: values.state,
              notification_method: values.notificationMethod || undefined,
              notification_body: values.notificationBody.trim() || undefined,
            });
          } catch (error) {
            applySimpleFormErrors(error, form.setError, {
              notification_body: "notificationBody",
              notification_method: "notificationMethod",
              state: "state",
            });
          }
        })}
      >
        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-state">
            Next state
          </label>
          <select
            id="admin-event-state"
            className="form-input"
            aria-invalid={form.formState.errors.state ? "true" : "false"}
            {...form.register("state")}
          >
            {allowedStates.map((state) => (
              <option key={state} value={state}>
                {formatEventState(state)}
              </option>
            ))}
          </select>
          {form.formState.errors.state ? (
            <p className="form-error">{form.formState.errors.state.message}</p>
          ) : null}
        </div>

        {selectedState === "cancelled" ? (
          <>
            <div className="form-field">
              <label className="form-label" htmlFor="admin-event-state-notification-method">
                Notification method
              </label>
              <select
                id="admin-event-state-notification-method"
                className="form-input"
                aria-invalid={form.formState.errors.notificationMethod ? "true" : "false"}
                {...form.register("notificationMethod")}
              >
                <option value="">Choose a method</option>
                <option value="in_app">In-app notification</option>
                <option value="email">Email</option>
              </select>
              {form.formState.errors.notificationMethod ? (
                <p className="form-error">{form.formState.errors.notificationMethod.message}</p>
              ) : null}
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="admin-event-state-notification-body">
                Cancellation notification body
              </label>
              <textarea
                id="admin-event-state-notification-body"
                rows={4}
                className="form-input form-textarea"
                aria-invalid={form.formState.errors.notificationBody ? "true" : "false"}
                {...form.register("notificationBody")}
              />
              {form.formState.errors.notificationBody ? (
                <p className="form-error">{form.formState.errors.notificationBody.message}</p>
              ) : null}
            </div>
          </>
        ) : null}

        <div className="panel__actions">
          <button
            type="submit"
            className="button-link button-link--primary"
            disabled={isPending}
          >
            {isPending ? "Applying..." : "Apply state change"}
          </button>
        </div>
      </form>
    </article>
  );
}

function OverflowRulePanel({
  currentRule,
  isPending,
  onSubmit,
}: {
  currentRule: OverflowRule;
  isPending: boolean;
  onSubmit: (payload: AdminEventOverflowRuleUpdateRequest) => Promise<void>;
}) {
  const form = useForm<OverflowRuleValues>({
    resolver: zodResolver(overflowRuleFormSchema),
    defaultValues: {
      overflowRule: currentRule,
      reason: "",
    },
  });

  return (
    <article className="detail-card">
      <div className="section-header">
        <div>
          <h2 className="detail-card__title">Overflow rule</h2>
          <p className="section-note">
            Overflow-rule changes use a dedicated backend endpoint and always require a reason.
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

          try {
            await onSubmit({
              overflow_rule: values.overflowRule,
              reason: values.reason.trim(),
            });
            form.reset({
              overflowRule: values.overflowRule,
              reason: "",
            });
          } catch (error) {
            applySimpleFormErrors(error, form.setError, {
              overflow_rule: "overflowRule",
              reason: "reason",
            });
          }
        })}
      >
        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-overflow-update">
            Overflow rule
          </label>
          <select
            id="admin-event-overflow-update"
            className="form-input"
            aria-invalid={form.formState.errors.overflowRule ? "true" : "false"}
            {...form.register("overflowRule")}
          >
            <option value="hard_rejection">Hard rejection</option>
            <option value="waitlist">Waitlist</option>
          </select>
          {form.formState.errors.overflowRule ? (
            <p className="form-error">{form.formState.errors.overflowRule.message}</p>
          ) : null}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-overflow-reason">
            Reason
          </label>
          <textarea
            id="admin-event-overflow-reason"
            rows={4}
            className="form-input form-textarea"
            aria-invalid={form.formState.errors.reason ? "true" : "false"}
            {...form.register("reason")}
          />
          {form.formState.errors.reason ? (
            <p className="form-error">{form.formState.errors.reason.message}</p>
          ) : null}
        </div>

        <div className="panel__actions">
          <button
            type="submit"
            className="button-link button-link--primary"
            disabled={isPending}
          >
            {isPending ? "Updating..." : "Update overflow rule"}
          </button>
        </div>
      </form>
    </article>
  );
}

type StateTransitionValues = {
  state: EventState;
  notificationMethod: "" | NotificationMethod;
  notificationBody: string;
};

type OverflowRuleValues = {
  overflowRule: OverflowRule;
  reason: string;
};

const overflowRuleFormSchema = z.object({
  overflowRule: overflowRuleSchema,
  reason: z.string().trim().min(1, "Reason is required."),
});

function buildStateTransitionSchema(allowedStates: EventState[]) {
  return z
    .object({
      state: z
        .enum(["draft", "published", "completed", "cancelled"])
        .refine((value) => allowedStates.includes(value), "Select a valid state transition."),
      notificationMethod: z.union([z.literal(""), notificationMethodSchema]).default(""),
      notificationBody: z.string().default(""),
    })
    .superRefine((values, context) => {
      if (values.state === "cancelled" && !values.notificationBody.trim()) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["notificationBody"],
          message: "Cancellation requires a notification body.",
        });
      }

      if (
        values.state !== "cancelled" &&
        (values.notificationMethod || values.notificationBody.trim())
      ) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["state"],
          message: "Notification settings are only allowed when cancelling an event.",
        });
      }
    });
}

function applySimpleFormErrors<TFieldName extends string>(
  error: unknown,
  setError: (name: TFieldName | "root", error: { type: string; message: string }) => void,
  mappings: Record<string, TFieldName>,
) {
  const apiError = error instanceof ApiError ? error : new ApiError("Could not save the changes.", { code: "unknown" });

  if (!apiError.fieldErrors || Object.keys(apiError.fieldErrors).length === 0) {
    setError("root", { type: "server", message: apiError.message });
    return;
  }

  let handledFieldError = false;

  for (const [field, messages] of Object.entries(apiError.fieldErrors)) {
    const message = messages[0];
    if (!message) {
      continue;
    }

    const mappedField = mappings[field];
    if (mappedField) {
      setError(mappedField, { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "form") {
      setError("root", { type: "server", message });
      handledFieldError = true;
    }
  }

  if (!handledFieldError) {
    setError("root", { type: "server", message: apiError.message });
  }
}

function getAllowedNextStates(state: EventState): EventState[] {
  if (state === "draft") {
    return ["published"];
  }
  if (state === "published") {
    return ["completed", "cancelled"];
  }
  return [];
}

function MetricCard({ label, value }: { label: string; value: number | string }) {
  return (
    <article className="metric-card">
      <p className="metric-card__label">{label}</p>
      <p className="metric-card__value">{value}</p>
    </article>
  );
}

function formatEventState(state: EventState): string {
  switch (state) {
    case "draft":
      return "Draft";
    case "published":
      return "Published";
    case "completed":
      return "Completed";
    case "cancelled":
      return "Cancelled";
  }
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
}
