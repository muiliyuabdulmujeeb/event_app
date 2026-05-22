import { useEffect, useMemo } from "react";
import type { InputHTMLAttributes } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { useForm, type UseFormRegisterReturn } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";

import { getAdminAnalyticsRegistrations } from "../api/adminAnalytics";
import { listAdminEvents } from "../api/adminEvents";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDate, formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import {
  adminAnalyticsRegistrationSortFields,
  analyticsPaymentStatusSchema,
  analyticsRegistrationStateSchema,
  type AdminAnalyticsRegistrationRow,
  type AdminAnalyticsRegistrationsParams,
  type AdminAnalyticsRegistrationsResponse,
  type AdminAnalyticsRegistrationSortBy,
  type AdminAnalyticsRegistrationSortField,
  type AdminAnalyticsSortOrder,
  type AnalyticsPaymentStatus,
  type AnalyticsRegistrationState,
} from "../types/adminAnalytics";
import type { AdminEventListResponse } from "../types/adminEvents";

const PAGE_SIZE = 50;

const filterFormSchema = z
  .object({
    event_ids: z.array(z.string()).default([]),
    date_from: z.string().default(""),
    date_to: z.string().default(""),
    state: z.union([analyticsRegistrationStateSchema, z.literal("")]).default(""),
    is_checked_in: z.enum(["", "true", "false"]).default(""),
    email: z.string().trim().default(""),
    first_name: z.string().trim().default(""),
    last_name: z.string().trim().default(""),
    is_batch: z.enum(["", "true", "false"]).default(""),
    payment_status: z.union([analyticsPaymentStatusSchema, z.literal("")]).default(""),
    paid_from: z.string().default(""),
    paid_to: z.string().default(""),
    amount_min: z.string().default(""),
    amount_max: z.string().default(""),
    custom_field_lines: z.string().default(""),
    sort_mode: z
      .union([
        z.enum(adminAnalyticsRegistrationSortFields),
        z.literal("custom_field"),
      ])
      .default("registered_at"),
    custom_sort_field_id: z.string().trim().default(""),
    sort_order: z.enum(["asc", "desc"]).default("desc"),
  })
  .superRefine((value, context) => {
    if (value.date_from && value.date_to && value.date_from > value.date_to) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["date_to"],
        message: "Registration end date must be on or after the start date.",
      });
    }

    if (value.paid_from && value.paid_to && value.paid_from > value.paid_to) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["paid_to"],
        message: "Paid date end must be on or after the start date.",
      });
    }

    const amountMin = parseOptionalInteger(value.amount_min);
    const amountMax = parseOptionalInteger(value.amount_max);

    if (value.amount_min && amountMin === undefined) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["amount_min"],
        message: "Minimum amount must be a whole number.",
      });
    }

    if (value.amount_max && amountMax === undefined) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["amount_max"],
        message: "Maximum amount must be a whole number.",
      });
    }

    if (
      amountMin !== undefined &&
      amountMax !== undefined &&
      amountMin > amountMax
    ) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["amount_max"],
        message: "Maximum amount must be greater than or equal to the minimum amount.",
      });
    }

    const customFieldLines = splitCustomFieldLines(value.custom_field_lines);
    for (const line of customFieldLines) {
      if (!line.includes(":")) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["custom_field_lines"],
          message: "Each custom field filter must use the format field_definition_id:value.",
        });
        break;
      }
    }

    if (value.sort_mode === "custom_field" && !value.custom_sort_field_id) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["custom_sort_field_id"],
        message: "Custom field sorting requires a field definition ID.",
      });
    }
  });

type FilterFormValues = z.infer<typeof filterFormSchema>;

export function AdminRegistrationsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const parsedSearchState = useMemo(
    () => parseSearchParams(searchParams),
    [searchParams],
  );

  const form = useForm<FilterFormValues>({
    resolver: zodResolver(filterFormSchema),
    defaultValues: buildFormValuesFromSearchState(parsedSearchState),
  });

  useEffect(() => {
    form.reset(buildFormValuesFromSearchState(parsedSearchState));
  }, [form, parsedSearchState]);

  const registrationsQuery = useQuery<AdminAnalyticsRegistrationsResponse, ApiError>({
    queryKey: queryKeys.analytics.registrations(parsedSearchState.query),
    queryFn: ({ signal }) =>
      getAdminAnalyticsRegistrations(parsedSearchState.query, signal),
  });

  const eventsQuery = useQuery<AdminEventListResponse, ApiError>({
    queryKey: queryKeys.adminEvents.all,
    queryFn: ({ signal }) => listAdminEvents(signal),
  });

  function handleApplyFilters(values: FilterFormValues) {
    const nextState = buildSearchStateFromFormValues(values, 1);
    setSearchParams(buildUrlSearchParams(nextState));
  }

  function handleResetFilters() {
    setSearchParams(buildUrlSearchParams(createDefaultSearchState()));
  }

  function handlePageChange(nextPage: number) {
    const boundedPage = Math.max(1, nextPage);
    setSearchParams(
      buildUrlSearchParams({
        ...parsedSearchState,
        page: boundedPage,
        query: {
          ...parsedSearchState.query,
          page: boundedPage,
        },
      }),
    );
  }

  const resultRange = getResultRange(
    registrationsQuery.data?.page ?? parsedSearchState.page,
    registrationsQuery.data?.page_size ?? PAGE_SIZE,
    registrationsQuery.data?.registrations.length ?? 0,
    registrationsQuery.data?.total ?? 0,
  );

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Registrations"
          description="Browse the analytics-backed registration table with backend-supported filters, sorting, and pagination. Responses are capped at 50 rows per page for a faster, slimmer admin view."
        />
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Filters and sorting</h2>
            <p className="section-note">
              Apply only the filters and sort fields supported by the admin analytics registrations endpoint.
            </p>
          </div>
        </div>

        <form className="admin-filters-form" onSubmit={form.handleSubmit(handleApplyFilters)} noValidate>
          <div className="form-grid admin-filters-grid">
            <div className="form-field">
              <label className="form-label" htmlFor="event_ids">
                Events
              </label>
              <select
                id="event_ids"
                multiple
                className="form-input form-input--multiselect"
                aria-invalid={Boolean(form.formState.errors.event_ids)}
                disabled={eventsQuery.isLoading || eventsQuery.isError}
                {...form.register("event_ids")}
              >
                {(eventsQuery.data?.events ?? []).map((event) => (
                  <option key={event.id} value={event.id}>
                    {event.title}
                  </option>
                ))}
              </select>
              <p className="field-hint">
                Hold Ctrl or Cmd to select multiple events. {eventsQuery.isError ? "Event options are unavailable right now." : "Leave empty to query across all events."}
              </p>
              {renderFieldError(form.formState.errors.event_ids?.message)}
            </div>

            <Field
              id="date_from"
              label="Registration date from"
              type="date"
              register={form.register("date_from")}
              error={form.formState.errors.date_from?.message}
            />
            <Field
              id="date_to"
              label="Registration date to"
              type="date"
              register={form.register("date_to")}
              error={form.formState.errors.date_to?.message}
            />

            <SelectField
              id="state"
              label="Registration state"
              register={form.register("state")}
              error={form.formState.errors.state?.message}
              options={[
                { label: "All states", value: "" },
                { label: "Confirmed", value: "confirmed" },
                { label: "Pending payment", value: "pending_payment" },
                { label: "Waitlisted", value: "waitlisted" },
                { label: "Cancelled", value: "cancelled" },
                { label: "Failed", value: "failed" },
              ]}
            />

            <SelectField
              id="is_checked_in"
              label="Check-in status"
              register={form.register("is_checked_in")}
              error={form.formState.errors.is_checked_in?.message}
              options={[
                { label: "All check-in states", value: "" },
                { label: "Checked in", value: "true" },
                { label: "Not checked in", value: "false" },
              ]}
            />

            <Field
              id="email"
              label="Attendee email"
              register={form.register("email")}
              error={form.formState.errors.email?.message}
            />
            <Field
              id="first_name"
              label="First name"
              register={form.register("first_name")}
              error={form.formState.errors.first_name?.message}
            />
            <Field
              id="last_name"
              label="Last name"
              register={form.register("last_name")}
              error={form.formState.errors.last_name?.message}
            />

            <SelectField
              id="is_batch"
              label="Batch status"
              register={form.register("is_batch")}
              error={form.formState.errors.is_batch?.message}
              options={[
                { label: "All registration types", value: "" },
                { label: "Batch registrations", value: "true" },
                { label: "Single registrations", value: "false" },
              ]}
            />

            <SelectField
              id="payment_status"
              label="Payment status"
              register={form.register("payment_status")}
              error={form.formState.errors.payment_status?.message}
              options={[
                { label: "All payment states", value: "" },
                { label: "Pending", value: "pending" },
                { label: "Successful", value: "successful" },
                { label: "Failed", value: "failed" },
              ]}
            />

            <Field
              id="paid_from"
              label="Paid date from"
              type="date"
              register={form.register("paid_from")}
              error={form.formState.errors.paid_from?.message}
            />
            <Field
              id="paid_to"
              label="Paid date to"
              type="date"
              register={form.register("paid_to")}
              error={form.formState.errors.paid_to?.message}
            />

            <Field
              id="amount_min"
              label="Minimum amount (NGN)"
              inputMode="numeric"
              register={form.register("amount_min")}
              error={form.formState.errors.amount_min?.message}
            />
            <Field
              id="amount_max"
              label="Maximum amount (NGN)"
              inputMode="numeric"
              register={form.register("amount_max")}
              error={form.formState.errors.amount_max?.message}
            />

            <div className="form-field admin-filters-grid__wide">
              <label className="form-label" htmlFor="custom_field_lines">
                Custom field filters
              </label>
              <textarea
                id="custom_field_lines"
                className="form-input form-textarea"
                rows={3}
                aria-invalid={Boolean(form.formState.errors.custom_field_lines)}
                {...form.register("custom_field_lines")}
              />
              <p className="field-hint">
                Enter one filter per line using <code>field_definition_id:value</code>.
              </p>
              {renderFieldError(form.formState.errors.custom_field_lines?.message)}
            </div>

            <SelectField
              id="sort_mode"
              label="Sort by"
              register={form.register("sort_mode")}
              error={form.formState.errors.sort_mode?.message}
              options={[
                { label: "Registered at", value: "registered_at" },
                { label: "Registration ID", value: "reg_id" },
                { label: "First name", value: "first_name" },
                { label: "Last name", value: "last_name" },
                { label: "Email", value: "email" },
                { label: "Registration state", value: "registration_state" },
                { label: "Checked in", value: "is_checked_in" },
                { label: "Checked in at", value: "checked_in_at" },
                { label: "Batch flag", value: "is_batch" },
                { label: "Event title", value: "event_title" },
                { label: "Event date", value: "event_date" },
                { label: "Amount paid", value: "amount_paid" },
                { label: "Payment status", value: "payment_status" },
                { label: "Paid at", value: "paid_at" },
                { label: "Custom field", value: "custom_field" },
              ]}
            />

            <Field
              id="custom_sort_field_id"
              label="Custom sort field definition ID"
              register={form.register("custom_sort_field_id")}
              error={form.formState.errors.custom_sort_field_id?.message}
              disabled={form.watch("sort_mode") !== "custom_field"}
            />

            <SelectField
              id="sort_order"
              label="Sort order"
              register={form.register("sort_order")}
              error={form.formState.errors.sort_order?.message}
              options={[
                { label: "Descending", value: "desc" },
                { label: "Ascending", value: "asc" },
              ]}
            />
          </div>

          {registrationsQuery.isError ? (
            <div className="form-alert" role="alert">
              {registrationsQuery.error.message}
            </div>
          ) : null}

          <div className="panel__actions">
            <button
              type="submit"
              className="button-link button-link--primary"
              disabled={form.formState.isSubmitting}
            >
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
            <h2 className="section-title">Registration table</h2>
            <p className="section-note">
              {registrationsQuery.data
                ? `Showing ${resultRange.from}-${resultRange.to} of ${registrationsQuery.data.total} registrations, 50 rows per page.`
                : "Query results will appear here once the analytics registration endpoint responds."}
            </p>
          </div>
        </div>

        {registrationsQuery.isPending ? (
          <LoadingState label="Loading registrations..." />
        ) : registrationsQuery.isError ? (
          <ErrorState
            title="Could not load registrations"
            message={registrationsQuery.error.message}
          />
        ) : registrationsQuery.data.registrations.length === 0 ? (
          <EmptyState
            title="No registrations matched the current filters"
            description="Adjust the current filters or clear them to broaden the analytics query."
          />
        ) : (
          <>
            <div className="table-wrap">
              <table className="data-table">
                <caption className="sr-only">
                  Admin registrations analytics table showing attendee, event, state, payment, operational flags, and expandable details.
                </caption>
                <thead>
                  <tr>
                    <th scope="col">Registration</th>
                    <th scope="col">Attendee</th>
                    <th scope="col">Event</th>
                    <th scope="col">State</th>
                    <th scope="col">Payment</th>
                    <th scope="col">Flags</th>
                    <th scope="col">Registered</th>
                    <th scope="col">Details</th>
                  </tr>
                </thead>
                <tbody>
                  {registrationsQuery.data.registrations.map((registration) => (
                    <tr key={registration.reg_id}>
                      <td>
                        <div className="table-cell-stack">
                          <strong>{registration.reg_id}</strong>
                          <span>{registration.is_batch ? "Batch registration" : "Single registration"}</span>
                        </div>
                      </td>
                      <td>
                        <div className="table-cell-stack">
                          <strong>
                            {registration.first_name} {registration.last_name}
                          </strong>
                          <span>{registration.email}</span>
                          {registration.batch_submitter_email ? (
                            <span>Submitter: {registration.batch_submitter_email}</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className="table-cell-stack">
                          <strong>{registration.event.title}</strong>
                          <span>{formatDateTime(registration.event.event_date)}</span>
                          <span>{registration.event.location}</span>
                        </div>
                      </td>
                      <td>
                        <div className="table-cell-stack">
                          <span>{formatRegistrationState(registration.registration_state)}</span>
                          <span>
                            {registration.is_checked_in
                              ? `Checked in ${formatDateTime(registration.checked_in_at)}`
                              : "Not checked in"}
                          </span>
                          {registration.refund_status ? (
                            <span>Refund: {formatLabel(registration.refund_status)}</span>
                          ) : null}
                        </div>
                      </td>
                      <td>
                        <div className="table-cell-stack">
                          {registration.payment ? (
                            <>
                              <strong>{formatCurrency(registration.payment.amount_paid, registration.payment.currency)}</strong>
                              <span>{registration.payment.payment_status ? formatLabel(registration.payment.payment_status) : "No payment state"}</span>
                              <span>{registration.payment.paid_at ? `Paid ${formatDateTime(registration.payment.paid_at)}` : "Not paid yet"}</span>
                            </>
                          ) : (
                            <>
                              <strong>{registration.event.is_free || registration.payment_waived ? "No charge" : "No payment record"}</strong>
                              <span>{registration.payment_waived ? "Payment waived" : registration.event.is_free ? "Free event" : "No payment summary"}</span>
                            </>
                          )}
                        </div>
                      </td>
                      <td>
                        <div className="registration-flags">
                          {registration.was_waitlisted ? (
                            <span className="status-pill status-pill--neutral">Was waitlisted</span>
                          ) : null}
                          {registration.used_exception_offer ? (
                            <span className="status-pill status-pill--neutral">Exception offer</span>
                          ) : null}
                          {registration.payment_waived ? (
                            <span className="status-pill status-pill--neutral">Waived</span>
                          ) : null}
                          {registration.capacity_override_applied ? (
                            <span className="status-pill status-pill--neutral">Capacity override</span>
                          ) : null}
                          {registration.is_checked_in ? (
                            <span className="status-pill status-pill--success">Checked in</span>
                          ) : null}
                        </div>
                      </td>
                      <td>{formatDateTime(registration.registered_at)}</td>
                      <td>
                        <details className="table-details">
                          <summary className="table-details__summary">View details</summary>
                          <div className="table-details__content">
                            {registration.previous_waitlist_position ? (
                              <p className="table-details__text">
                                Previous waitlist position: {registration.previous_waitlist_position}
                              </p>
                            ) : null}
                            {registration.cancellation_reason ? (
                              <p className="table-details__text">
                                Cancellation reason: {formatLabel(registration.cancellation_reason)}
                              </p>
                            ) : null}
                            {registration.batch_submitter_name ? (
                              <p className="table-details__text">
                                Batch submitter: {registration.batch_submitter_name}
                              </p>
                            ) : null}
                            {registration.payment?.payment_reference ? (
                              <p className="table-details__text">
                                Payment reference: {registration.payment.payment_reference}
                              </p>
                            ) : null}
                            {registration.custom_fields.length > 0 ? (
                              <ul className="mini-detail-list">
                                {registration.custom_fields.map((field) => (
                                  <li key={`${registration.reg_id}-${field.label}`}>
                                    <strong>{field.label}:</strong> {field.value || "--"}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p className="table-details__text">No custom field values recorded.</p>
                            )}
                          </div>
                        </details>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="pagination-bar">
              <p className="section-note">
                Page {registrationsQuery.data.page} of {Math.max(1, Math.ceil(registrationsQuery.data.total / registrationsQuery.data.page_size))}
              </p>
              <div className="panel__actions">
                <button
                  type="button"
                  className="button-link"
                  onClick={() => handlePageChange(parsedSearchState.page - 1)}
                  disabled={parsedSearchState.page <= 1}
                >
                  Previous
                </button>
                <button
                  type="button"
                  className="button-link"
                  onClick={() => handlePageChange(parsedSearchState.page + 1)}
                  disabled={resultRange.to >= registrationsQuery.data.total}
                >
                  Next
                </button>
              </div>
            </div>
          </>
        )}
      </section>
    </div>
  );
}

type SearchState = {
  event_ids: string[];
  date_from: string;
  date_to: string;
  state: "" | AnalyticsRegistrationState;
  is_checked_in: "" | "true" | "false";
  email: string;
  first_name: string;
  last_name: string;
  is_batch: "" | "true" | "false";
  payment_status: "" | AnalyticsPaymentStatus;
  paid_from: string;
  paid_to: string;
  amount_min: string;
  amount_max: string;
  custom_field_lines: string;
  sort_mode: AdminAnalyticsRegistrationSortField | "custom_field";
  custom_sort_field_id: string;
  sort_order: AdminAnalyticsSortOrder;
  page: number;
  query: AdminAnalyticsRegistrationsParams;
};

function createDefaultSearchState(): SearchState {
  return {
    event_ids: [],
    date_from: "",
    date_to: "",
    state: "",
    is_checked_in: "",
    email: "",
    first_name: "",
    last_name: "",
    is_batch: "",
    payment_status: "",
    paid_from: "",
    paid_to: "",
    amount_min: "",
    amount_max: "",
    custom_field_lines: "",
    sort_mode: "registered_at",
    custom_sort_field_id: "",
    sort_order: "desc",
    page: 1,
    query: {
      page: 1,
      page_size: PAGE_SIZE,
      sort_by: "registered_at",
      sort_order: "desc",
    },
  };
}

function parseSearchParams(searchParams: URLSearchParams): SearchState {
  const defaultState = createDefaultSearchState();
  const eventIds = uniqueNonEmpty(searchParams.getAll("event_ids"));
  const customFieldFilters = uniqueNonEmpty(searchParams.getAll("custom_field"));
  const sortBy = (searchParams.get("sort_by") || "registered_at").trim();
  const isCustomSort = sortBy.startsWith("custom_field:");
  const customSortFieldId = isCustomSort ? sortBy.slice("custom_field:".length).trim() : "";
  const sortMode: SearchState["sort_mode"] = isCustomSort
    ? "custom_field"
    : isKnownSortField(sortBy)
      ? sortBy
      : "registered_at";
  const sortOrder = searchParams.get("sort_order") === "asc" ? "asc" : "desc";
  const page = parsePositiveInteger(searchParams.get("page")) ?? 1;

  const query: AdminAnalyticsRegistrationsParams = {
    page,
    page_size: PAGE_SIZE,
    sort_by: isCustomSort
      ? customSortFieldId
        ? (`custom_field:${customSortFieldId}` as AdminAnalyticsRegistrationSortBy)
        : "registered_at"
      : sortMode === "custom_field"
        ? "registered_at"
        : sortMode,
    sort_order: sortOrder,
  };

  if (eventIds.length > 0) {
    query.event_ids = eventIds;
  }

  const dateFrom = searchParams.get("date_from")?.trim() || "";
  if (dateFrom) {
    query.date_from = dateFrom;
  }

  const dateTo = searchParams.get("date_to")?.trim() || "";
  if (dateTo) {
    query.date_to = dateTo;
  }

  const state = parseRegistrationState(searchParams.get("state"));
  if (state) {
    query.state = state;
  }

  const isCheckedIn = parseBooleanString(searchParams.get("is_checked_in"));
  if (isCheckedIn !== "") {
    query.is_checked_in = isCheckedIn === "true";
  }

  const email = searchParams.get("email")?.trim() || "";
  if (email) {
    query.email = email;
  }

  const firstName = searchParams.get("first_name")?.trim() || "";
  if (firstName) {
    query.first_name = firstName;
  }

  const lastName = searchParams.get("last_name")?.trim() || "";
  if (lastName) {
    query.last_name = lastName;
  }

  const isBatch = parseBooleanString(searchParams.get("is_batch"));
  if (isBatch !== "") {
    query.is_batch = isBatch === "true";
  }

  const paymentStatus = parsePaymentStatus(searchParams.get("payment_status"));
  if (paymentStatus) {
    query.payment_status = paymentStatus;
  }

  const paidFrom = searchParams.get("paid_from")?.trim() || "";
  if (paidFrom) {
    query.paid_from = paidFrom;
  }

  const paidTo = searchParams.get("paid_to")?.trim() || "";
  if (paidTo) {
    query.paid_to = paidTo;
  }

  const amountMin = parseNonNegativeInteger(searchParams.get("amount_min"));
  if (amountMin !== undefined) {
    query.amount_min = amountMin;
  }

  const amountMax = parseNonNegativeInteger(searchParams.get("amount_max"));
  if (amountMax !== undefined) {
    query.amount_max = amountMax;
  }

  if (customFieldFilters.length > 0) {
    query.custom_field = customFieldFilters;
  }

  return {
    ...defaultState,
    event_ids: eventIds,
    date_from: dateFrom,
    date_to: dateTo,
    state: state ?? "",
    is_checked_in: isCheckedIn,
    email,
    first_name: firstName,
    last_name: lastName,
    is_batch: isBatch,
    payment_status: paymentStatus ?? "",
    paid_from: paidFrom,
    paid_to: paidTo,
    amount_min: amountMin === undefined ? "" : String(amountMin),
    amount_max: amountMax === undefined ? "" : String(amountMax),
    custom_field_lines: customFieldFilters.join("\n"),
    sort_mode: sortMode,
    custom_sort_field_id: customSortFieldId,
    sort_order: sortOrder,
    page,
    query,
  };
}

function buildFormValuesFromSearchState(state: SearchState): FilterFormValues {
  return {
    event_ids: state.event_ids,
    date_from: state.date_from,
    date_to: state.date_to,
    state: state.state,
    is_checked_in: state.is_checked_in,
    email: state.email,
    first_name: state.first_name,
    last_name: state.last_name,
    is_batch: state.is_batch,
    payment_status: state.payment_status,
    paid_from: state.paid_from,
    paid_to: state.paid_to,
    amount_min: state.amount_min,
    amount_max: state.amount_max,
    custom_field_lines: state.custom_field_lines,
    sort_mode: state.sort_mode,
    custom_sort_field_id: state.custom_sort_field_id,
    sort_order: state.sort_order,
  };
}

function buildSearchStateFromFormValues(
  values: FilterFormValues,
  page: number,
): SearchState {
  const eventIds = uniqueNonEmpty(values.event_ids);
  const customFieldFilters = splitCustomFieldLines(values.custom_field_lines);
  const customSortFieldId = values.custom_sort_field_id.trim();
  const sortBy =
    values.sort_mode === "custom_field"
      ? (`custom_field:${customSortFieldId}` as AdminAnalyticsRegistrationSortBy)
      : values.sort_mode;

  const query: AdminAnalyticsRegistrationsParams = {
    page,
    page_size: PAGE_SIZE,
    sort_by: sortBy,
    sort_order: values.sort_order,
  };

  if (eventIds.length > 0) {
    query.event_ids = eventIds;
  }
  if (values.date_from) {
    query.date_from = values.date_from;
  }
  if (values.date_to) {
    query.date_to = values.date_to;
  }
  if (values.state) {
    query.state = values.state;
  }
  if (values.is_checked_in) {
    query.is_checked_in = values.is_checked_in === "true";
  }
  if (values.email.trim()) {
    query.email = values.email.trim();
  }
  if (values.first_name.trim()) {
    query.first_name = values.first_name.trim();
  }
  if (values.last_name.trim()) {
    query.last_name = values.last_name.trim();
  }
  if (values.is_batch) {
    query.is_batch = values.is_batch === "true";
  }
  if (values.payment_status) {
    query.payment_status = values.payment_status;
  }
  if (values.paid_from) {
    query.paid_from = values.paid_from;
  }
  if (values.paid_to) {
    query.paid_to = values.paid_to;
  }

  const amountMin = parseOptionalInteger(values.amount_min);
  if (amountMin !== undefined) {
    query.amount_min = amountMin;
  }

  const amountMax = parseOptionalInteger(values.amount_max);
  if (amountMax !== undefined) {
    query.amount_max = amountMax;
  }

  if (customFieldFilters.length > 0) {
    query.custom_field = customFieldFilters;
  }

  return {
    event_ids: eventIds,
    date_from: values.date_from,
    date_to: values.date_to,
    state: values.state,
    is_checked_in: values.is_checked_in,
    email: values.email.trim(),
    first_name: values.first_name.trim(),
    last_name: values.last_name.trim(),
    is_batch: values.is_batch,
    payment_status: values.payment_status,
    paid_from: values.paid_from,
    paid_to: values.paid_to,
    amount_min: values.amount_min.trim(),
    amount_max: values.amount_max.trim(),
    custom_field_lines: customFieldFilters.join("\n"),
    sort_mode: values.sort_mode,
    custom_sort_field_id: customSortFieldId,
    sort_order: values.sort_order,
    page,
    query,
  };
}

function buildUrlSearchParams(state: SearchState): URLSearchParams {
  const params = new URLSearchParams();

  for (const eventId of state.event_ids) {
    params.append("event_ids", eventId);
  }

  appendUrlParam(params, "date_from", state.date_from);
  appendUrlParam(params, "date_to", state.date_to);
  appendUrlParam(params, "state", state.state);
  appendUrlParam(params, "is_checked_in", state.is_checked_in);
  appendUrlParam(params, "email", state.email);
  appendUrlParam(params, "first_name", state.first_name);
  appendUrlParam(params, "last_name", state.last_name);
  appendUrlParam(params, "is_batch", state.is_batch);
  appendUrlParam(params, "payment_status", state.payment_status);
  appendUrlParam(params, "paid_from", state.paid_from);
  appendUrlParam(params, "paid_to", state.paid_to);
  appendUrlParam(params, "amount_min", state.amount_min);
  appendUrlParam(params, "amount_max", state.amount_max);

  for (const customFieldFilter of splitCustomFieldLines(state.custom_field_lines)) {
    params.append("custom_field", customFieldFilter);
  }

  params.set("page", String(state.page));
  params.set(
    "sort_by",
    state.sort_mode === "custom_field"
      ? `custom_field:${state.custom_sort_field_id}`
      : state.sort_mode,
  );
  params.set("sort_order", state.sort_order);

  return params;
}

function getResultRange(
  page: number,
  pageSize: number,
  currentCount: number,
  total: number,
) {
  if (currentCount === 0 || total === 0) {
    return { from: 0, to: 0 };
  }

  const from = (page - 1) * pageSize + 1;
  const to = Math.min(from + currentCount - 1, total);
  return { from, to };
}

function parseRegistrationState(
  value: string | null,
): AnalyticsRegistrationState | null {
  const parsed = analyticsRegistrationStateSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

function parsePaymentStatus(value: string | null): AnalyticsPaymentStatus | null {
  const parsed = analyticsPaymentStatusSchema.safeParse(value);
  return parsed.success ? parsed.data : null;
}

function parseBooleanString(value: string | null): "" | "true" | "false" {
  if (value === "true" || value === "false") {
    return value;
  }
  return "";
}

function parseOptionalInteger(value: string): number | undefined {
  const trimmed = value.trim();
  if (!trimmed) {
    return undefined;
  }

  if (!/^\d+$/.test(trimmed)) {
    return undefined;
  }

  return Number(trimmed);
}

function parsePositiveInteger(value: string | null): number | undefined {
  if (!value?.trim() || !/^\d+$/.test(value.trim())) {
    return undefined;
  }

  const parsed = Number(value.trim());
  return parsed > 0 ? parsed : undefined;
}

function parseNonNegativeInteger(value: string | null): number | undefined {
  if (!value?.trim() || !/^\d+$/.test(value.trim())) {
    return undefined;
  }

  return Number(value.trim());
}

function splitCustomFieldLines(value: string): string[] {
  return uniqueNonEmpty(
    value
      .split(/\r?\n/)
      .map((item) => item.trim()),
  );
}

function uniqueNonEmpty(values: string[]): string[] {
  return Array.from(new Set(values.filter((value) => value.trim())));
}

function appendUrlParam(
  params: URLSearchParams,
  key: string,
  value: string,
) {
  if (value.trim()) {
    params.set(key, value.trim());
  }
}

function isKnownSortField(
  value: string,
): value is AdminAnalyticsRegistrationSortField {
  return (
    adminAnalyticsRegistrationSortFields as readonly string[]
  ).includes(value);
}

function formatRegistrationState(
  value: AnalyticsRegistrationState,
): string {
  if (value === "pending_payment") {
    return "Pending payment";
  }

  if (value === "waitlisted") {
    return "Waitlisted";
  }

  return formatLabel(value);
}

function formatLabel(value: string): string {
  return value
    .replace(/_/g, " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

function renderFieldError(message?: string) {
  return message ? (
    <p className="form-error" role="alert">
      {message}
    </p>
  ) : null;
}

type FieldProps = {
  id: string;
  label: string;
  error?: string;
  type?: string;
  disabled?: boolean;
  inputMode?: InputHTMLAttributes<HTMLInputElement>["inputMode"];
  register: UseFormRegisterReturn;
};

function Field({
  id,
  label,
  error,
  type = "text",
  disabled,
  inputMode,
  register,
}: FieldProps) {
  return (
    <div className="form-field">
      <label className="form-label" htmlFor={id}>
        {label}
      </label>
      <input
        id={id}
        type={type}
        className="form-input"
        aria-invalid={Boolean(error)}
        disabled={disabled}
        inputMode={inputMode}
        {...register}
      />
      {renderFieldError(error)}
    </div>
  );
}

type SelectFieldProps = {
  id: string;
  label: string;
  error?: string;
  register: UseFormRegisterReturn;
  options: Array<{ label: string; value: string }>;
};

function SelectField({ id, label, error, register, options }: SelectFieldProps) {
  return (
    <div className="form-field">
      <label className="form-label" htmlFor={id}>
        {label}
      </label>
      <select id={id} className="form-input" aria-invalid={Boolean(error)} {...register}>
        {options.map((option) => (
          <option key={`${id}-${option.value || "empty"}`} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {renderFieldError(error)}
    </div>
  );
}
