import { useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { useSearchParams } from "react-router-dom";

import {
  checkInRegistration,
  searchStaffRegistrations,
  uncheckInRegistration,
} from "../api/staff";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type {
  StaffCheckInResponse,
  StaffRegistrationResult,
  StaffRegistrationSearchResponse,
} from "../types/staff";

const searchModeSchema = z.enum(["reg_id", "email"]);
const emailRegex = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;

const searchSchema = z
  .object({
    mode: searchModeSchema,
    query: z.string().trim().min(1, "Search value is required."),
  })
  .superRefine((values, context) => {
    if (values.mode === "email" && !emailRegex.test(values.query)) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["query"],
        message: "Enter a valid email address.",
      });
    }
  });

type SearchFormValues = z.infer<typeof searchSchema>;
type SearchMode = z.infer<typeof searchModeSchema>;
type ActiveSearch = { mode: SearchMode; value: string } | null;

export function StaffRegistrationsPage() {
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const [actionError, setActionError] = useState<{ regId: string; message: string } | null>(null);

  const activeSearch = useMemo<ActiveSearch>(() => {
    const regId = searchParams.get("reg_id")?.trim() ?? "";
    const email = searchParams.get("email")?.trim() ?? "";
    if (Boolean(regId) === Boolean(email)) {
      return null;
    }
    if (regId) {
      return { mode: "reg_id", value: regId };
    }
    return { mode: "email", value: email };
  }, [searchParams]);

  const form = useForm<SearchFormValues>({
    resolver: zodResolver(searchSchema),
    defaultValues: {
      mode: activeSearch?.mode ?? "reg_id",
      query: activeSearch?.value ?? "",
    },
  });

  const watchMode = form.watch("mode");

  const activeSearchParams = useMemo(
    () =>
      activeSearch
        ? {
            regId: activeSearch.mode === "reg_id" ? activeSearch.value : undefined,
            email: activeSearch.mode === "email" ? activeSearch.value : undefined,
          }
        : null,
    [activeSearch],
  );

  const registrationsQuery = useQuery<StaffRegistrationSearchResponse, ApiError>({
    queryKey: queryKeys.staff.registrations(activeSearchParams ?? {}),
    queryFn: ({ signal }) =>
      searchStaffRegistrations(
        {
          regId: activeSearchParams?.regId,
          email: activeSearchParams?.email,
        },
        signal,
      ),
    enabled: activeSearchParams !== null,
  });

  const checkInMutation = useMutation<StaffCheckInResponse, ApiError, string>({
    mutationFn: checkInRegistration,
    onSuccess: (response) => {
      if (!activeSearchParams) {
        return;
      }

      queryClient.setQueryData<StaffRegistrationSearchResponse | undefined>(
        queryKeys.staff.registrations(activeSearchParams),
        (current) => applyCheckInUpdate(current, response),
      );
    },
  });

  const uncheckInMutation = useMutation<StaffCheckInResponse, ApiError, string>({
    mutationFn: uncheckInRegistration,
    onSuccess: (response) => {
      if (!activeSearchParams) {
        return;
      }

      queryClient.setQueryData<StaffRegistrationSearchResponse | undefined>(
        queryKeys.staff.registrations(activeSearchParams),
        (current) => applyCheckInUpdate(current, response),
      );
    },
  });

  const pendingCheckInRegId = checkInMutation.isPending ? checkInMutation.variables ?? null : null;
  const pendingUncheckRegId = uncheckInMutation.isPending
    ? uncheckInMutation.variables ?? null
    : null;

  const handleSubmit = form.handleSubmit((values) => {
    setActionError(null);
    const nextValue = values.query.trim();
    if (values.mode === "reg_id") {
      setSearchParams({ reg_id: nextValue });
      return;
    }

    setSearchParams({ email: nextValue });
  });

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Staff"
          title="Registration operations"
          description="Search by registration ID or attendee email, then use server-confirmed check-in actions on the matching results."
        />

        <form className="auth-form" onSubmit={handleSubmit} noValidate>
          <fieldset className="choice-group">
            <legend className="form-label">Search by</legend>
            <div className="choice-group__options">
              <label className="choice-option" htmlFor="search-mode-reg-id">
                <input
                  id="search-mode-reg-id"
                  type="radio"
                  value="reg_id"
                  {...form.register("mode")}
                />
                <span>Registration ID</span>
              </label>
              <label className="choice-option" htmlFor="search-mode-email">
                <input
                  id="search-mode-email"
                  type="radio"
                  value="email"
                  {...form.register("mode")}
                />
                <span>Email</span>
              </label>
            </div>
          </fieldset>

          <div className="form-field">
            <label className="form-label" htmlFor="staff-search-query">
              {watchMode === "email" ? "Email address" : "Registration ID"}
            </label>
            <input
              id="staff-search-query"
              type={watchMode === "email" ? "email" : "text"}
              autoComplete="off"
              placeholder={
                watchMode === "email"
                  ? "attendee@example.com"
                  : "Enter a registration ID"
              }
              className="form-input"
              aria-invalid={form.formState.errors.query ? "true" : "false"}
              {...form.register("query")}
            />
            {form.formState.errors.query ? (
              <p className="form-error">{form.formState.errors.query.message}</p>
            ) : null}
          </div>

          <div className="panel__actions">
            <button type="submit" className="button-link button-link--primary">
              Search registrations
            </button>
          </div>
        </form>
      </section>

      {!activeSearchParams ? (
        <EmptyState
          title="No search submitted yet"
          description="Search by a registration ID or attendee email to load the operational record."
        />
      ) : null}

      {activeSearchParams && registrationsQuery.isPending ? (
        <LoadingState label="Loading registration results..." />
      ) : null}

      {activeSearchParams && registrationsQuery.isError ? (
        <ErrorState
          title={
            registrationsQuery.error.code === "forbidden"
              ? "Access denied"
              : registrationsQuery.error.code === "notFound"
                ? "Registration not found"
                : "Could not load registration results"
          }
          message={registrationsQuery.error.message}
        />
      ) : null}

      {registrationsQuery.isSuccess && registrationsQuery.data.total === 0 ? (
        <EmptyState
          title="No registrations matched"
          description="No accessible registrations matched the submitted search."
        />
      ) : null}

      {registrationsQuery.isSuccess && registrationsQuery.data.total > 0 ? (
        <section className="panel">
          <div className="section-header">
            <h2 className="section-title">Search results</h2>
            <p className="section-note">
              {registrationsQuery.data.total} registration
              {registrationsQuery.data.total === 1 ? "" : "s"} matched the current search.
            </p>
          </div>

          <div className="result-list">
            {registrationsQuery.data.registrations.map((registration) => (
              <StaffRegistrationCard
                key={registration.reg_id}
                registration={registration}
                actionError={
                  actionError?.regId === registration.reg_id ? actionError.message : null
                }
                checkInPending={pendingCheckInRegId === registration.reg_id}
                uncheckPending={pendingUncheckRegId === registration.reg_id}
                onCheckIn={() => {
                  setActionError(null);
                  checkInMutation.mutate(registration.reg_id, {
                    onError: (error) => {
                      setActionError({ regId: registration.reg_id, message: error.message });
                    },
                  });
                }}
                onUncheckIn={() => {
                  setActionError(null);
                  uncheckInMutation.mutate(registration.reg_id, {
                    onError: (error) => {
                      setActionError({ regId: registration.reg_id, message: error.message });
                    },
                  });
                }}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function StaffRegistrationCard({
  registration,
  actionError,
  checkInPending,
  uncheckPending,
  onCheckIn,
  onUncheckIn,
}: {
  registration: StaffRegistrationResult;
  actionError: string | null;
  checkInPending: boolean;
  uncheckPending: boolean;
  onCheckIn: () => void;
  onUncheckIn: () => void;
}) {
  const canCheckIn = registration.state === "confirmed" && !registration.is_checked_in;
  const canUncheck = registration.is_checked_in;

  return (
    <article className="result-card">
      <div className="result-card__header">
        <div>
          <h3 className="result-card__title">
            {registration.first_name} {registration.last_name}
          </h3>
          <p className="result-card__meta">
            {registration.reg_id} | {registration.email}
          </p>
        </div>
        <div className="panel__actions">
          {canCheckIn ? (
            <button
              type="button"
              className="button-link button-link--primary"
              onClick={onCheckIn}
              disabled={checkInPending}
            >
              {checkInPending ? "Checking in..." : "Check in"}
            </button>
          ) : null}
          {canUncheck ? (
            <button
              type="button"
              className="button-link"
              onClick={onUncheckIn}
              disabled={uncheckPending}
            >
              {uncheckPending ? "Reversing..." : "Reverse check-in"}
            </button>
          ) : null}
          {!canCheckIn && !canUncheck ? (
            <p className="detail-card__text">No check-in action is available for the current state.</p>
          ) : null}
        </div>
      </div>

      {actionError ? (
        <div className="form-alert" role="alert">
          {actionError}
        </div>
      ) : null}

      <div className="result-card__grid">
        <section className="detail-section">
          <h4 className="detail-section__title">Registration</h4>
          <dl className="detail-list">
            <div>
              <dt>Status</dt>
              <dd>{formatRegistrationState(registration.state)}</dd>
            </div>
            <div>
              <dt>Checked in</dt>
              <dd>
                {registration.is_checked_in
                  ? `Yes${registration.checked_in_at ? ` | ${formatDateTime(registration.checked_in_at)}` : ""}`
                  : "No"}
              </dd>
            </div>
            <div>
              <dt>Registered at</dt>
              <dd>{formatDateTime(registration.registered_at)}</dd>
            </div>
            <div>
              <dt>Batch registration</dt>
              <dd>{registration.is_batch ? "Yes" : "No"}</dd>
            </div>
          </dl>
        </section>

        <section className="detail-section">
          <h4 className="detail-section__title">Event</h4>
          <dl className="detail-list">
            <div>
              <dt>Title</dt>
              <dd>{registration.event.title}</dd>
            </div>
            <div>
              <dt>Date</dt>
              <dd>{formatDateTime(registration.event.event_date)}</dd>
            </div>
            <div>
              <dt>Location</dt>
              <dd>{registration.event.location}</dd>
            </div>
            <div>
              <dt>Event state</dt>
              <dd>{formatEventState(registration.event.state)}</dd>
            </div>
            <div>
              <dt>Pricing</dt>
              <dd>{registration.event.is_free ? "Free" : "Paid"}</dd>
            </div>
            <div>
              <dt>Capacity overrides</dt>
              <dd>{registration.event.capacity_override_count}</dd>
            </div>
          </dl>
        </section>

        <section className="detail-section">
          <h4 className="detail-section__title">Payment</h4>
          {registration.payment ? (
            <dl className="detail-list">
              <div>
                <dt>Status</dt>
                <dd>{formatPaymentStatus(registration.payment.status)}</dd>
              </div>
              <div>
                <dt>Amount</dt>
                <dd>{formatPrice(registration.payment.amount_paid, registration.payment.currency)}</dd>
              </div>
              <div>
                <dt>Paid at</dt>
                <dd>
                  {registration.payment.paid_at
                    ? formatDateTime(registration.payment.paid_at)
                    : "Not paid"}
                </dd>
              </div>
            </dl>
          ) : (
            <p className="detail-card__text">No payment summary is available for this registration.</p>
          )}
        </section>

        <section className="detail-section">
          <h4 className="detail-section__title">Custom field values</h4>
          {registration.custom_field_values.length > 0 ? (
            <div className="custom-value-list">
              {registration.custom_field_values.map((field) => (
                <article className="custom-value-card" key={`${registration.reg_id}-${field.label}`}>
                  <h5 className="custom-value-card__title">{field.label}</h5>
                  <p className="custom-value-card__value">{field.value}</p>
                </article>
              ))}
            </div>
          ) : (
            <p className="detail-card__text">No custom field values were recorded for this registration.</p>
          )}
        </section>
      </div>
    </article>
  );
}

function applyCheckInUpdate(
  current: StaffRegistrationSearchResponse | undefined,
  response: StaffCheckInResponse,
): StaffRegistrationSearchResponse | undefined {
  if (!current) {
    return current;
  }

  return {
    ...current,
    registrations: current.registrations.map((registration) =>
      registration.reg_id === response.reg_id
        ? {
            ...registration,
            state: response.state,
            is_checked_in: response.is_checked_in,
            checked_in_at: response.checked_in_at,
          }
        : registration,
    ),
  };
}

function formatRegistrationState(state: StaffRegistrationResult["state"]): string {
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

function formatEventState(state: StaffRegistrationResult["event"]["state"]): string {
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

function formatPaymentStatus(
  status: NonNullable<StaffRegistrationResult["payment"]>["status"],
): string {
  switch (status) {
    case "pending":
      return "Pending";
    case "successful":
      return "Successful";
    case "failed":
      return "Failed";
  }
}

function formatPrice(amount: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}
