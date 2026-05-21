import { useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useSearchParams } from "react-router-dom";
import { z } from "zod";

import {
  cancelRegistration,
  createRefundRequest,
  initializeRegistrationPayment,
  lookupRegistration,
  markRegistrationNotificationSeen,
} from "../api/publicRegistrations";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDate, formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type {
  RegistrationLookupPromotionOffer,
  RegistrationLookupResponse,
  RegistrationPaymentInitializationResponse,
  RefundRequestStatus,
  UserNotification,
} from "../types/registrations";

const lookupSchema = z.object({
  regId: z
    .string()
    .trim()
    .min(1, "Registration ID is required.")
    .max(18, "Registration ID must be 18 characters or fewer."),
});

const optionalReasonSchema = z.object({
  reason: z.string().trim().max(1000, "Reason is too long.").optional(),
});

type LookupFormValues = z.infer<typeof lookupSchema>;
type OptionalReasonFormValues = z.infer<typeof optionalReasonSchema>;

export function RegistrationLookupPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const initialRegId = searchParams.get("reg_id")?.trim() ?? "";
  const [paymentInitializationResult, setPaymentInitializationResult] =
    useState<RegistrationPaymentInitializationResponse | null>(null);
  const queryClient = useQueryClient();

  const lookupForm = useForm<LookupFormValues>({
    resolver: zodResolver(lookupSchema),
    defaultValues: {
      regId: initialRegId,
    },
  });

  const cancelForm = useForm<OptionalReasonFormValues>({
    resolver: zodResolver(optionalReasonSchema),
    defaultValues: { reason: "" },
  });

  const refundForm = useForm<OptionalReasonFormValues>({
    resolver: zodResolver(optionalReasonSchema),
    defaultValues: { reason: "" },
  });

  const submittedRegId = useMemo(() => searchParams.get("reg_id")?.trim() ?? "", [searchParams]);

  const lookupQuery = useQuery<RegistrationLookupResponse, ApiError>({
    queryKey: queryKeys.registrations.lookup(submittedRegId),
    queryFn: ({ signal }) => lookupRegistration(submittedRegId, signal),
    enabled: submittedRegId.length > 0,
  });

  const markSeenMutation = useMutation({
    mutationFn: markRegistrationNotificationSeen,
    onSuccess: (response) => {
      if (!submittedRegId) {
        return;
      }

      queryClient.setQueryData<RegistrationLookupResponse | undefined>(
        queryKeys.registrations.lookup(submittedRegId),
        (current) => {
          if (!current) {
            return current;
          }

          return {
            ...current,
            notifications: current.notifications.filter(
              (notification) => notification.id !== response.id,
            ),
          };
        },
      );
    },
  });

  const cancelMutation = useMutation({
    mutationFn: (values: OptionalReasonFormValues) =>
      cancelRegistration(submittedRegId, { reason: values.reason?.trim() || undefined }),
    onSuccess: async () => {
      setPaymentInitializationResult(null);
      cancelForm.reset({ reason: "" });
      if (submittedRegId) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.registrations.lookup(submittedRegId),
        });
      }
    },
    onError: (error: ApiError) => {
      cancelForm.setError("root", {
        type: "server",
        message: error.message,
      });
    },
  });

  const refundMutation = useMutation({
    mutationFn: (values: OptionalReasonFormValues) =>
      createRefundRequest(submittedRegId, { reason: values.reason?.trim() || undefined }),
    onSuccess: async () => {
      refundForm.reset({ reason: "" });
      if (submittedRegId) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.registrations.lookup(submittedRegId),
        });
      }
    },
    onError: (error: ApiError) => {
      refundForm.setError("root", {
        type: "server",
        message: error.message,
      });
    },
  });

  const paymentInitializationMutation = useMutation({
    mutationFn: () => initializeRegistrationPayment(submittedRegId),
    onSuccess: async (response) => {
      setPaymentInitializationResult(response);
      if (submittedRegId) {
        await queryClient.invalidateQueries({
          queryKey: queryKeys.registrations.lookup(submittedRegId),
        });
      }
    },
  });

  const handleLookupSubmit = lookupForm.handleSubmit((values) => {
    const nextRegId = values.regId.trim();
    setPaymentInitializationResult(null);
    setSearchParams(nextRegId ? { reg_id: nextRegId } : {});
    cancelForm.reset({ reason: "" });
    refundForm.reset({ reason: "" });
  });

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Public"
          title="Registration lookup"
          description="Enter a registration ID to view its current state, unread notifications, payment summary, and any available self-service actions."
        />

        <form className="lookup-form" onSubmit={handleLookupSubmit} noValidate>
          <div className="form-field lookup-form__field">
            <label className="form-label" htmlFor="registration-lookup-id">
              Registration ID
            </label>
            <input
              id="registration-lookup-id"
              type="text"
              autoComplete="off"
              placeholder="Example: EVT-2026-ABC123"
              className="form-input"
              aria-invalid={lookupForm.formState.errors.regId ? "true" : "false"}
              {...lookupForm.register("regId")}
            />
            {lookupForm.formState.errors.regId ? (
              <p className="form-error">{lookupForm.formState.errors.regId.message}</p>
            ) : null}
          </div>

          <div className="panel__actions lookup-form__actions">
            <button type="submit" className="button-link button-link--primary">
              Find registration
            </button>
          </div>
        </form>
      </section>

      {!submittedRegId ? (
        <EmptyState
          title="No registration loaded yet"
          description="Use a registration ID to load the current status and any user-facing updates."
        />
      ) : null}

      {submittedRegId && lookupQuery.isPending ? (
        <LoadingState label="Loading registration details…" />
      ) : null}

      {submittedRegId && lookupQuery.isError ? (
        <ErrorState
          title={lookupQuery.error.code === "notFound" ? "Registration not found" : "Could not load this registration"}
          message={lookupQuery.error.message}
        />
      ) : null}

      {lookupQuery.isSuccess ? (
        <RegistrationLookupResult
          data={lookupQuery.data}
          markSeenPendingId={markSeenMutation.variables ?? null}
          onMarkSeen={(notificationId) => markSeenMutation.mutate(notificationId)}
          cancelForm={cancelForm}
          cancelPending={cancelMutation.isPending}
          onCancelSubmit={cancelForm.handleSubmit((values) => cancelMutation.mutate(values))}
          refundForm={refundForm}
          refundPending={refundMutation.isPending}
          onRefundSubmit={refundForm.handleSubmit((values) => refundMutation.mutate(values))}
          paymentInitializationResult={paymentInitializationResult}
          paymentInitializationPending={paymentInitializationMutation.isPending}
          paymentInitializationError={paymentInitializationMutation.error?.message ?? null}
          onInitializePayment={() => {
            setPaymentInitializationResult(null);
            paymentInitializationMutation.mutate();
          }}
        />
      ) : null}
    </div>
  );
}

function RegistrationLookupResult({
  data,
  markSeenPendingId,
  onMarkSeen,
  cancelForm,
  cancelPending,
  onCancelSubmit,
  refundForm,
  refundPending,
  onRefundSubmit,
  paymentInitializationResult,
  paymentInitializationPending,
  paymentInitializationError,
  onInitializePayment,
}: {
  data: RegistrationLookupResponse;
  markSeenPendingId: string | null;
  onMarkSeen: (notificationId: string) => void;
  cancelForm: ReturnType<typeof useForm<OptionalReasonFormValues>>;
  cancelPending: boolean;
  onCancelSubmit: (event?: React.BaseSyntheticEvent) => Promise<void>;
  refundForm: ReturnType<typeof useForm<OptionalReasonFormValues>>;
  refundPending: boolean;
  onRefundSubmit: (event?: React.BaseSyntheticEvent) => Promise<void>;
  paymentInitializationResult: RegistrationPaymentInitializationResponse | null;
  paymentInitializationPending: boolean;
  paymentInitializationError: string | null;
  onInitializePayment: () => void;
}) {
  const { registration, event, payment, promotion_offer, refund_request, notifications } = data;
  const canAttemptCancellation =
    !registration.is_checked_in &&
    (registration.state === "confirmed" ||
      registration.state === "pending_payment" ||
      registration.state === "waitlisted");
  const canAttemptPaymentRecovery =
    event.is_free === false &&
    registration.is_batch === false &&
    registration.state === "pending_payment";

  const canAttemptRefund =
    registration.state === "cancelled" &&
    event.is_free === false &&
    payment?.status === "successful" &&
    (refund_request === null || refund_request.status === "rejected");

  return (
    <>
      <section className="panel">
        <PageHeader
          eyebrow="Registration summary"
          title={`${registration.first_name} ${registration.last_name}`}
          description="This view reflects the current public lookup payload returned by the backend."
        />

        <div className="lookup-grid">
          <article className="detail-card">
            <h2 className="detail-card__title">Registration</h2>
            <dl className="detail-list">
              <div>
                <dt>Registration ID</dt>
                <dd>{registration.reg_id}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{formatRegistrationState(registration.state)}</dd>
              </div>
              <div>
                <dt>Email</dt>
                <dd>{registration.email}</dd>
              </div>
              <div>
                <dt>Registered at</dt>
                <dd>{formatDateTime(registration.registered_at)}</dd>
              </div>
              <div>
                <dt>Batch registration</dt>
                <dd>{registration.is_batch ? "Yes" : "No"}</dd>
              </div>
              <div>
                <dt>Checked in</dt>
                <dd>
                  {registration.is_checked_in
                    ? `Yes${registration.checked_in_at ? ` · ${formatDateTime(registration.checked_in_at)}` : ""}`
                    : "No"}
                </dd>
              </div>
            </dl>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Event</h2>
            <dl className="detail-list">
              <div>
                <dt>Title</dt>
                <dd>{event.title}</dd>
              </div>
              <div>
                <dt>Date</dt>
                <dd>{formatDateTime(event.event_date)}</dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{event.location}</dd>
              </div>
              <div>
                <dt>Pricing</dt>
                <dd>{event.is_free ? "Free" : "Paid"}</dd>
              </div>
              <div>
                <dt>Event state</dt>
                <dd>{formatEventState(event.state)}</dd>
              </div>
            </dl>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Payment, refund, and waitlist context</h2>
          <p className="section-note">Only data the backend currently exposes is shown here.</p>
        </div>

        <div className="lookup-grid">
          <article className="detail-card">
            <h3 className="detail-card__title">Payment</h3>
            {payment ? (
              <dl className="detail-list">
                <div>
                  <dt>Status</dt>
                  <dd>{formatPaymentStatus(payment.status)}</dd>
                </div>
                <div>
                  <dt>Amount</dt>
                  <dd>{formatPrice(payment.amount_paid, payment.currency)}</dd>
                </div>
                <div>
                  <dt>Paid at</dt>
                  <dd>{payment.paid_at ? formatDateTime(payment.paid_at) : "Not yet paid"}</dd>
                </div>
              </dl>
            ) : (
              <p className="detail-card__text">No payment summary is available for this registration.</p>
            )}

            {canAttemptPaymentRecovery ? (
              <div className="detail-card__actions">
                {paymentInitializationError ? (
                  <div className="form-alert" role="alert">
                    {paymentInitializationError}
                  </div>
                ) : null}

                {paymentInitializationResult ? (
                  <div className="action-feedback">
                    <p className="action-feedback__title">{paymentInitializationResult.message}</p>
                    <p className="action-feedback__meta">
                      Reference: {paymentInitializationResult.payment_reference}
                    </p>
                    <div className="panel__actions">
                      <a
                        href={paymentInitializationResult.checkout_url}
                        className="button-link button-link--primary"
                      >
                        Continue to payment
                      </a>
                    </div>
                  </div>
                ) : null}

                <div className="panel__actions">
                  <button
                    type="button"
                    className="button-link button-link--primary"
                    onClick={onInitializePayment}
                    disabled={paymentInitializationPending}
                  >
                    {paymentInitializationPending ? "Preparing payment link..." : "Get fresh payment link"}
                  </button>
                </div>
              </div>
            ) : null}
          </article>

          <article className="detail-card">
            <h3 className="detail-card__title">Refund request</h3>
            {refund_request ? (
              <dl className="detail-list">
                <div>
                  <dt>Status</dt>
                  <dd>{formatRefundStatus(refund_request.status)}</dd>
                </div>
                <div>
                  <dt>Requested at</dt>
                  <dd>{formatDateTime(refund_request.requested_at)}</dd>
                </div>
                <div>
                  <dt>Processed at</dt>
                  <dd>{refund_request.processed_at ? formatDateTime(refund_request.processed_at) : "Pending"}</dd>
                </div>
              </dl>
            ) : (
              <p className="detail-card__text">No refund request is currently associated with this registration.</p>
            )}
          </article>

          <article className="detail-card">
            <h3 className="detail-card__title">Waitlist history</h3>
            {registration.was_waitlisted || registration.previous_waitlist_position !== null ? (
              <dl className="detail-list">
                <div>
                  <dt>Previously waitlisted</dt>
                  <dd>{registration.was_waitlisted ? "Yes" : "No"}</dd>
                </div>
                <div>
                  <dt>Previous waitlist position</dt>
                  <dd>{registration.previous_waitlist_position ?? "—"}</dd>
                </div>
                <div>
                  <dt>Cancellation reason</dt>
                  <dd>{registration.cancellation_reason ? formatCancellationReason(registration.cancellation_reason) : "—"}</dd>
                </div>
              </dl>
            ) : (
              <p className="detail-card__text">No waitlist history is currently recorded for this registration.</p>
            )}
          </article>

          <article className="detail-card">
            <h3 className="detail-card__title">Promotion offer</h3>
            {promotion_offer ? (
              <PromotionOfferSummary offer={promotion_offer} />
            ) : (
              <p className="detail-card__text">No active or historical waitlist promotion offer is attached.</p>
            )}
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Custom field values</h2>
          <p className="section-note">These are the event-specific values captured during registration.</p>
        </div>

        {registration.custom_field_values.length > 0 ? (
          <div className="custom-value-list">
            {registration.custom_field_values.map((field) => (
              <article className="custom-value-card" key={field.label}>
                <h3 className="custom-value-card__title">{field.label}</h3>
                <p className="custom-value-card__value">{field.value}</p>
              </article>
            ))}
          </div>
        ) : (
          <p className="detail-card__text">No custom field values were recorded for this registration.</p>
        )}
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Unread notifications</h2>
          <p className="section-note">The backend lookup endpoint returns only unseen user notifications.</p>
        </div>

        {notifications.length > 0 ? (
          <div className="notification-list">
            {notifications.map((notification) => (
              <article className="notification-card" key={notification.id}>
                <div className="notification-card__content">
                  <h3 className="notification-card__title">{notification.title}</h3>
                  <p className="notification-card__meta">{formatDateTime(notification.created_at)}</p>
                  <p className="notification-card__body">{notification.body}</p>
                </div>
                <div className="notification-card__actions">
                  <button
                    type="button"
                    className="button-link"
                    onClick={() => onMarkSeen(notification.id)}
                    disabled={markSeenPendingId === notification.id}
                  >
                    {markSeenPendingId === notification.id ? "Updating…" : "Mark as seen"}
                  </button>
                </div>
              </article>
            ))}
          </div>
        ) : (
          <p className="detail-card__text">There are no unseen notifications for this registration right now.</p>
        )}
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Self-service actions</h2>
          <p className="section-note">These actions are only shown when the current lookup state makes them reasonable to attempt.</p>
        </div>

        <div className="lookup-grid">
          <article className="detail-card">
            <h3 className="detail-card__title">Cancel registration</h3>
            {canAttemptCancellation ? (
              <form className="action-form" onSubmit={onCancelSubmit} noValidate>
                {cancelForm.formState.errors.root?.message ? (
                  <div className="form-alert" role="alert">{cancelForm.formState.errors.root.message}</div>
                ) : null}
                <div className="form-field">
                  <label className="form-label" htmlFor="cancel-reason">
                    Reason (optional)
                  </label>
                  <textarea
                    id="cancel-reason"
                    rows={4}
                    className="form-input form-textarea"
                    {...cancelForm.register("reason")}
                  />
                </div>
                <div className="panel__actions">
                  <button type="submit" className="button-link button-link--primary" disabled={cancelPending}>
                    {cancelPending ? "Cancelling…" : "Cancel registration"}
                  </button>
                </div>
              </form>
            ) : (
              <p className="detail-card__text">
                Cancellation is not currently available for this registration state.
              </p>
            )}
          </article>

          <article className="detail-card">
            <h3 className="detail-card__title">Request refund</h3>
            {canAttemptRefund ? (
              <form className="action-form" onSubmit={onRefundSubmit} noValidate>
                {refundForm.formState.errors.root?.message ? (
                  <div className="form-alert" role="alert">{refundForm.formState.errors.root.message}</div>
                ) : null}
                <div className="form-field">
                  <label className="form-label" htmlFor="refund-reason">
                    Reason (optional)
                  </label>
                  <textarea
                    id="refund-reason"
                    rows={4}
                    className="form-input form-textarea"
                    {...refundForm.register("reason")}
                  />
                </div>
                <div className="panel__actions">
                  <button type="submit" className="button-link button-link--primary" disabled={refundPending}>
                    {refundPending ? "Submitting…" : "Submit refund request"}
                  </button>
                </div>
              </form>
            ) : (
              <p className="detail-card__text">
                Refund request submission is not currently available from the visible lookup state.
              </p>
            )}
          </article>
        </div>
      </section>
    </>
  );
}

function PromotionOfferSummary({ offer }: { offer: RegistrationLookupPromotionOffer }) {
  return (
    <div className="summary-stack">
      <dl className="detail-list">
        <div>
          <dt>Status</dt>
          <dd>{formatPromotionOfferStatus(offer.status)}</dd>
        </div>
        <div>
          <dt>Offer expires</dt>
          <dd>{formatDateTime(offer.offer_expires_at)}</dd>
        </div>
      </dl>

      {offer.payment_action_url ? (
        <div className="panel__actions">
          <a href={offer.payment_action_url} className="button-link button-link--primary">
            Continue promotion payment
          </a>
        </div>
      ) : (
        <p className="detail-card__text">No payment action is currently available for this offer.</p>
      )}
    </div>
  );
}

function formatRegistrationState(state: RegistrationLookupResponse["registration"]["state"]): string {
  switch (state) {
    case "confirmed":
      return "Confirmed";
    case "pending_payment":
      return "Pending payment";
    case "waitlisted":
      return "Waitlisted";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
  }
}

function formatEventState(state: RegistrationLookupResponse["event"]["state"]): string {
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

function formatPaymentStatus(status: RegistrationLookupResponse["payment"] extends infer T ? T extends { status: infer S } ? S : never : never): string {
  switch (status) {
    case "pending":
      return "Pending";
    case "successful":
      return "Successful";
    case "failed":
      return "Failed";
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

function formatPromotionOfferStatus(status: RegistrationLookupPromotionOffer["status"]): string {
  switch (status) {
    case "offered":
      return "Offered";
    case "payment_initialized":
      return "Payment initialized";
    case "paid":
      return "Paid";
    case "failed":
      return "Failed";
    case "expired":
      return "Expired";
    case "cancelled":
      return "Cancelled";
    case "manual_review":
      return "Manual review";
  }
}

function formatCancellationReason(reason: NonNullable<RegistrationLookupResponse["registration"]["cancellation_reason"]>): string {
  switch (reason) {
    case "user_cancelled":
      return "User cancelled";
    case "overflow_rule_changed":
      return "Overflow rule changed";
  }
}

function formatPrice(amount: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}
