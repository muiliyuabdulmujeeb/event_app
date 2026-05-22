import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";

import { listAdminEvents } from "../api/adminEvents";
import {
  listAdminRefundRequests,
  updateAdminRefundRequest,
} from "../api/adminRefunds";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import {
  refundRequestStatusSchema,
  type AdminRefundRequestListResponse,
  type AdminRefundRequestSummary,
  type AdminRefundRequestUpdateRequest,
  type AdminRefundRequestUpdateResponse,
  type RefundRequestStatus,
} from "../types/adminRefunds";
import type { NotificationMethod } from "../types/adminNotifications";
import type { AdminEventListResponse } from "../types/adminEvents";

const refundFilterFormSchema = z.object({
  status: z.union([refundRequestStatusSchema, z.literal("")]).default(""),
  eventId: z.string().trim().default(""),
  regId: z.string().trim().default(""),
});

const refundUpdateFormSchema = z.object({
  status: z.union([
    z.literal("approved"),
    z.literal("rejected"),
    z.literal("completed"),
  ]),
  notification_method: z.union([z.literal("in_app"), z.literal("email")]),
  message_body: z.string().trim().min(1, "Enter the message body."),
  title: z.string().trim().max(255).optional().or(z.literal("")),
  resolution_notes: z.string().trim().max(1000).optional().or(z.literal("")),
});

type RefundFilterFormValues = z.infer<typeof refundFilterFormSchema>;
type RefundUpdateFormValues = z.infer<typeof refundUpdateFormSchema>;

export function AdminRefundsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const activeFilters = useMemo(() => parseRefundSearchParams(searchParams), [searchParams]);

  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const eventsQuery = useQuery<AdminEventListResponse, ApiError>({
    queryKey: queryKeys.adminEvents.all,
    queryFn: ({ signal }) => listAdminEvents(signal),
  });

  const refundsQuery = useQuery<AdminRefundRequestListResponse, ApiError>({
    queryKey: queryKeys.refunds.list({
      status: activeFilters.status,
      eventId: activeFilters.eventId,
      regId: activeFilters.regId,
    }),
    queryFn: ({ signal }) =>
      listAdminRefundRequests(
        {
          status: activeFilters.status || undefined,
          eventId: activeFilters.eventId || undefined,
          regId: activeFilters.regId || undefined,
        },
        signal,
      ),
  });

  const filterForm = useForm<RefundFilterFormValues>({
    resolver: zodResolver(refundFilterFormSchema),
    defaultValues: activeFilters,
  });

  useEffect(() => {
    filterForm.reset(activeFilters);
  }, [activeFilters, filterForm]);

  function handleApplyFilters(values: RefundFilterFormValues) {
    const nextSearchParams = new URLSearchParams();
    if (values.status) {
      nextSearchParams.set("status", values.status);
    }
    if (values.eventId.trim()) {
      nextSearchParams.set("event_id", values.eventId.trim());
    }
    if (values.regId.trim()) {
      nextSearchParams.set("reg_id", values.regId.trim());
    }
    setSearchParams(nextSearchParams);
  }

  function handleResetFilters() {
    setSearchParams(new URLSearchParams());
    setStatusMessage(null);
  }

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Refund requests"
          description="Review refund requests from the real backend list and move them through the allowed admin status transitions with the required notification payload."
        />
      </section>

      {statusMessage ? (
        <section className="action-feedback" role="status">
          <p className="action-feedback__title">{statusMessage}</p>
        </section>
      ) : null}

      <section className="panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Refund filters</h2>
            <p className="section-note">
              Filter only by the backend-supported refund list query params.
            </p>
          </div>
        </div>

        <form
          className="auth-form"
          noValidate
          onSubmit={filterForm.handleSubmit(handleApplyFilters)}
        >
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label" htmlFor="refund-filter-status">
                Refund status
              </label>
              <select
                id="refund-filter-status"
                className="form-input"
                {...filterForm.register("status")}
              >
                <option value="">All statuses</option>
                <option value="requested">Requested</option>
                <option value="approved">Approved</option>
                <option value="rejected">Rejected</option>
                <option value="completed">Completed</option>
              </select>
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="refund-filter-event">
                Event
              </label>
              {eventsQuery.isPending ? (
                <LoadingState label="Loading events..." />
              ) : eventsQuery.isError ? (
                <div className="form-alert" role="alert">
                  {eventsQuery.error.message}
                </div>
              ) : (
                <select
                  id="refund-filter-event"
                  className="form-input"
                  {...filterForm.register("eventId")}
                >
                  <option value="">All events</option>
                  {eventsQuery.data.events.map((event) => (
                    <option key={event.id} value={event.id}>
                      {event.title}
                    </option>
                  ))}
                </select>
              )}
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="refund-filter-reg-id">
                Registration ID
              </label>
              <input
                id="refund-filter-reg-id"
                type="text"
                autoComplete="off"
                className="form-input"
                {...filterForm.register("regId")}
              />
            </div>
          </div>

          <div className="panel__actions">
            <button type="submit" className="button-link button-link--primary">
              Apply filters
            </button>
            <button type="button" className="button-link" onClick={handleResetFilters}>
              Reset filters
            </button>
          </div>
        </form>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Refund queue</h2>
            <p className="section-note">
              {refundsQuery.data
                ? `${refundsQuery.data.total} refund request${refundsQuery.data.total === 1 ? "" : "s"} loaded from the admin refund list endpoint.`
                : "Refund request rows will appear here once the backend list resolves."}
            </p>
          </div>
        </div>

        {refundsQuery.isPending ? (
          <LoadingState label="Loading refund requests..." />
        ) : refundsQuery.isError ? (
          <ErrorState
            title="Could not load refund requests"
            message={refundsQuery.error.message}
          />
        ) : refundsQuery.data.items.length === 0 ? (
          <EmptyState
            title="No refund requests matched the current filters"
            description="Adjust the current refund filters or clear them to broaden the backend query."
          />
        ) : (
          <div className="result-list">
            {refundsQuery.data.items.map((refundRequest) => (
              <RefundRequestCard
                key={refundRequest.refund_request_id}
                refundRequest={refundRequest}
                onSuccess={(message) => {
                  setStatusMessage(message);
                  void queryClient.invalidateQueries({
                    queryKey: queryKeys.refunds.list({
                      status: activeFilters.status || undefined,
                      eventId: activeFilters.eventId || undefined,
                      regId: activeFilters.regId || undefined,
                    }),
                    exact: true,
                  });
                }}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

function RefundRequestCard({
  refundRequest,
  onSuccess,
}: {
  refundRequest: AdminRefundRequestSummary;
  onSuccess: (message: string) => void;
}) {
  const allowedTransitions = useMemo(
    () => getAllowedRefundTransitions(refundRequest.status),
    [refundRequest.status],
  );
  const form = useForm<RefundUpdateFormValues>({
    resolver: zodResolver(refundUpdateFormSchema),
    defaultValues: {
      status: allowedTransitions[0] ?? "approved",
      notification_method: "in_app",
      message_body: "",
      title: "",
      resolution_notes: "",
    },
  });

  useEffect(() => {
    form.reset({
      status: allowedTransitions[0] ?? "approved",
      notification_method: "in_app",
      message_body: "",
      title: "",
      resolution_notes: "",
    });
  }, [allowedTransitions, form, refundRequest.refund_request_id]);

  const mutation = useMutation<
    AdminRefundRequestUpdateResponse,
    ApiError,
    AdminRefundRequestUpdateRequest
  >({
    mutationFn: (payload) =>
      updateAdminRefundRequest(refundRequest.refund_request_id, payload),
    onSuccess: (response) => {
      form.reset({
        status: getAllowedRefundTransitions(response.status)[0] ?? "approved",
        notification_method: "in_app",
        message_body: "",
        title: "",
        resolution_notes: "",
      });
      onSuccess(response.message);
    },
  });

  return (
    <article className="result-card">
      <div className="result-card__header">
        <div>
          <h3 className="result-card__title">{refundRequest.refund_request_id}</h3>
          <p className="result-card__meta">Registration: {refundRequest.reg_id}</p>
        </div>
        <span className="status-pill">{formatRefundStatus(refundRequest.status)}</span>
      </div>

      <div className="result-card__grid">
        <section className="detail-section">
          <h4 className="detail-section__title">Request timing</h4>
          <dl className="detail-list">
            <div>
              <dt>Requested</dt>
              <dd>{formatDateTime(refundRequest.requested_at)}</dd>
            </div>
            <div>
              <dt>Processed</dt>
              <dd>
                {refundRequest.processed_at
                  ? formatDateTime(refundRequest.processed_at)
                  : "Not processed yet"}
              </dd>
            </div>
          </dl>
        </section>
      </div>

      {allowedTransitions.length === 0 ? (
        <EmptyState
          title="No further admin action is available"
          description="This refund request is already in a terminal state and cannot be updated again through the backend."
        />
      ) : (
        <details className="table-details">
          <summary className="table-details__summary">Update refund request</summary>
          <div className="table-details__content">
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
                  await mutation.mutateAsync({
                    status: values.status,
                    notification_method: values.notification_method as NotificationMethod,
                    message_body: values.message_body.trim(),
                    title: values.title?.trim() || undefined,
                    resolution_notes: values.resolution_notes?.trim() || undefined,
                  });
                } catch (error) {
                  applyRefundUpdateErrors(error, form.setError);
                }
              })}
            >
              <div className="form-grid">
                <div className="form-field">
                  <label className="form-label" htmlFor={`refund-status-${refundRequest.refund_request_id}`}>
                    Next status
                  </label>
                  <select
                    id={`refund-status-${refundRequest.refund_request_id}`}
                    className="form-input"
                    aria-invalid={form.formState.errors.status ? "true" : "false"}
                    {...form.register("status")}
                  >
                    {allowedTransitions.map((status) => (
                      <option key={status} value={status}>
                        {formatRefundStatus(status)}
                      </option>
                    ))}
                  </select>
                  {form.formState.errors.status ? (
                    <p className="form-error">{form.formState.errors.status.message}</p>
                  ) : null}
                </div>

                <div className="form-field">
                  <label className="form-label" htmlFor={`refund-method-${refundRequest.refund_request_id}`}>
                    Notification method
                  </label>
                  <select
                    id={`refund-method-${refundRequest.refund_request_id}`}
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

                <div className="form-field">
                  <label className="form-label" htmlFor={`refund-title-${refundRequest.refund_request_id}`}>
                    Title
                  </label>
                  <input
                    id={`refund-title-${refundRequest.refund_request_id}`}
                    type="text"
                    className="form-input"
                    aria-invalid={form.formState.errors.title ? "true" : "false"}
                    {...form.register("title")}
                  />
                  <p className="field-hint">
                    Leave blank to let the backend apply its default title for this status.
                  </p>
                  {form.formState.errors.title ? (
                    <p className="form-error">{form.formState.errors.title.message}</p>
                  ) : null}
                </div>
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor={`refund-message-${refundRequest.refund_request_id}`}>
                  Message body
                </label>
                <textarea
                  id={`refund-message-${refundRequest.refund_request_id}`}
                  className="form-input form-textarea"
                  rows={4}
                  aria-invalid={form.formState.errors.message_body ? "true" : "false"}
                  {...form.register("message_body")}
                />
                {form.formState.errors.message_body ? (
                  <p className="form-error">{form.formState.errors.message_body.message}</p>
                ) : null}
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor={`refund-notes-${refundRequest.refund_request_id}`}>
                  Resolution notes
                </label>
                <textarea
                  id={`refund-notes-${refundRequest.refund_request_id}`}
                  className="form-input form-textarea"
                  rows={3}
                  aria-invalid={form.formState.errors.resolution_notes ? "true" : "false"}
                  {...form.register("resolution_notes")}
                />
                {form.formState.errors.resolution_notes ? (
                  <p className="form-error">
                    {form.formState.errors.resolution_notes.message}
                  </p>
                ) : null}
              </div>

              <div className="panel__actions">
                <button
                  type="submit"
                  className="button-link button-link--primary"
                  disabled={mutation.isPending}
                >
                  {mutation.isPending ? "Updating..." : "Update refund request"}
                </button>
              </div>
            </form>
          </div>
        </details>
      )}
    </article>
  );
}

function parseRefundSearchParams(searchParams: URLSearchParams): RefundFilterFormValues {
  const parsedStatus = refundRequestStatusSchema.safeParse(
    searchParams.get("status") ?? "",
  );

  return {
    status: parsedStatus.success ? parsedStatus.data : "",
    eventId: searchParams.get("event_id")?.trim() ?? "",
    regId: searchParams.get("reg_id")?.trim() ?? "",
  };
}

function getAllowedRefundTransitions(
  status: RefundRequestStatus,
): Array<Exclude<RefundRequestStatus, "requested">> {
  switch (status) {
    case "requested":
      return ["approved", "rejected", "completed"];
    case "approved":
      return ["rejected", "completed"];
    case "rejected":
    case "completed":
      return [];
  }
}

function formatRefundStatus(status: RefundRequestStatus): string {
  switch (status) {
    case "requested":
      return "Requested";
    case "approved":
      return "Approved";
    case "rejected":
      return "Rejected";
    case "completed":
      return "Completed";
  }
}

function applyRefundUpdateErrors(
  error: unknown,
  setError: ReturnType<typeof useForm<RefundUpdateFormValues>>["setError"],
) {
  const apiError =
    error instanceof ApiError
      ? error
      : new ApiError("Could not update the refund request.", { code: "unknown" });

  if (!apiError.fieldErrors || Object.keys(apiError.fieldErrors).length === 0) {
    setError("root", { type: "server", message: apiError.message });
    return;
  }

  let handled = false;
  const fieldMap: Record<string, keyof RefundUpdateFormValues> = {
    status: "status",
    notification_method: "notification_method",
    message_body: "message_body",
    title: "title",
    resolution_notes: "resolution_notes",
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
