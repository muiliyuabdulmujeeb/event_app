import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { useSearchParams } from "react-router-dom";
import { z } from "zod";

import {
  downloadAdminAnalytics,
  getAdminAnalyticsSummary,
} from "../api/adminAnalytics";
import { listAdminEvents } from "../api/adminEvents";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDate } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type {
  AdminAnalyticsDownloadParams,
  AdminAnalyticsSummaryParams,
  AdminAnalyticsSummaryResponse,
  AnalyticsDownloadFormat,
} from "../types/adminAnalytics";
import type { AdminEventListResponse } from "../types/adminEvents";

const analyticsFilterSchema = z
  .object({
    event_ids: z.array(z.string()).default([]),
    date_from: z.string().default(""),
    date_to: z.string().default(""),
  })
  .superRefine((value, context) => {
    if (value.date_from && value.date_to && value.date_from > value.date_to) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["date_to"],
        message: "End date must be on or after the start date.",
      });
    }
  });

type AnalyticsFilterFormValues = z.infer<typeof analyticsFilterSchema>;

export function AdminAnalyticsPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [statusMessage, setStatusMessage] = useState<string | null>(null);
  const activeFilters = useMemo(() => parseAnalyticsSearchParams(searchParams), [searchParams]);

  const eventsQuery = useQuery<AdminEventListResponse, ApiError>({
    queryKey: queryKeys.adminEvents.all,
    queryFn: ({ signal }) => listAdminEvents(signal),
  });

  const summaryQuery = useQuery<AdminAnalyticsSummaryResponse, ApiError>({
    queryKey: queryKeys.analytics.summary(activeFilters),
    queryFn: ({ signal }) => getAdminAnalyticsSummary(activeFilters, signal),
  });

  const form = useForm<AnalyticsFilterFormValues>({
    resolver: zodResolver(analyticsFilterSchema),
    defaultValues: {
      event_ids: activeFilters.event_ids ?? [],
      date_from: activeFilters.date_from ?? "",
      date_to: activeFilters.date_to ?? "",
    },
  });

  useEffect(() => {
    form.reset({
      event_ids: activeFilters.event_ids ?? [],
      date_from: activeFilters.date_from ?? "",
      date_to: activeFilters.date_to ?? "",
    });
  }, [activeFilters, form]);

  const downloadMutation = useMutation<
    { blob: Blob; filename: string; contentType: string },
    ApiError,
    AnalyticsDownloadFormat
  >({
    mutationFn: async (format) =>
      downloadAdminAnalytics({
        format,
        ...activeFilters,
      }),
    onSuccess: (result, format) => {
      triggerBrowserDownload(result.blob, result.filename);
      setStatusMessage(
        `${format.toUpperCase()} export is ready using the current analytics scope.`,
      );
    },
  });

  function handleApplyFilters(values: AnalyticsFilterFormValues) {
    const nextSearchParams = new URLSearchParams();

    for (const eventId of uniqueNonEmpty(values.event_ids)) {
      nextSearchParams.append("event_ids", eventId);
    }

    if (values.date_from) {
      nextSearchParams.set("date_from", values.date_from);
    }

    if (values.date_to) {
      nextSearchParams.set("date_to", values.date_to);
    }

    setStatusMessage(null);
    setSearchParams(nextSearchParams);
  }

  function handleResetFilters() {
    setStatusMessage(null);
    setSearchParams(new URLSearchParams());
  }

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Analytics"
          description="Review the backend analytics summary for the current scope, then export CSV or PDF files directly through the admin analytics download endpoint."
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
            <h2 className="section-title">Scope and exports</h2>
            <p className="section-note">
              These filters match the current analytics summary endpoint. Export actions use the same scope.
            </p>
          </div>
        </div>

        {form.formState.errors.root?.message ? (
          <div className="form-alert" role="alert">
            {form.formState.errors.root.message}
          </div>
        ) : null}

        <form
          className="admin-filters-form"
          noValidate
          onSubmit={form.handleSubmit(handleApplyFilters)}
        >
          <div className="form-grid admin-filters-grid">
            <div className="form-field admin-filters-grid__wide">
              <label className="form-label" htmlFor="admin-analytics-events">
                Events
              </label>
              {eventsQuery.isPending ? (
                <LoadingState label="Loading event options..." />
              ) : eventsQuery.isError ? (
                <div className="form-alert" role="alert">
                  {eventsQuery.error.message}
                </div>
              ) : (
                <>
                  <select
                    id="admin-analytics-events"
                    multiple
                    className="form-input form-input--multiselect"
                    {...form.register("event_ids")}
                  >
                    {eventsQuery.data.events.map((event) => (
                      <option key={event.id} value={event.id}>
                        {event.title}
                      </option>
                    ))}
                  </select>
                  <p className="field-hint">
                    Hold Ctrl or Cmd to select multiple events. Leave empty to summarize every accessible event.
                  </p>
                </>
              )}
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="admin-analytics-date-from">
                Date from
              </label>
              <input
                id="admin-analytics-date-from"
                type="date"
                className="form-input"
                aria-invalid={form.formState.errors.date_from ? "true" : "false"}
                {...form.register("date_from")}
              />
              {form.formState.errors.date_from ? (
                <p className="form-error">{form.formState.errors.date_from.message}</p>
              ) : null}
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="admin-analytics-date-to">
                Date to
              </label>
              <input
                id="admin-analytics-date-to"
                type="date"
                className="form-input"
                aria-invalid={form.formState.errors.date_to ? "true" : "false"}
                {...form.register("date_to")}
              />
              {form.formState.errors.date_to ? (
                <p className="form-error">{form.formState.errors.date_to.message}</p>
              ) : null}
            </div>
          </div>

          <div className="panel__actions">
            <button type="submit" className="button-link button-link--primary">
              Apply scope
            </button>
            <button type="button" className="button-link" onClick={handleResetFilters}>
              Reset scope
            </button>
            <button
              type="button"
              className="button-link"
              onClick={() => {
                setStatusMessage(null);
                downloadMutation.mutate("csv");
              }}
              disabled={downloadMutation.isPending}
            >
              {downloadMutation.isPending && downloadMutation.variables === "csv"
                ? "Preparing CSV..."
                : "Download CSV"}
            </button>
            <button
              type="button"
              className="button-link"
              onClick={() => {
                setStatusMessage(null);
                downloadMutation.mutate("pdf");
              }}
              disabled={downloadMutation.isPending}
            >
              {downloadMutation.isPending && downloadMutation.variables === "pdf"
                ? "Preparing PDF..."
                : "Download PDF"}
            </button>
          </div>

          {downloadMutation.isError ? (
            <div className="form-alert" role="alert">
              {downloadMutation.error.message}
            </div>
          ) : null}
        </form>
      </section>

      {summaryQuery.isPending ? (
        <LoadingState label="Loading analytics summary..." />
      ) : summaryQuery.isError ? (
        <ErrorState
          title="Could not load analytics"
          message={summaryQuery.error.message}
        />
      ) : (
        <>
          <section className="metric-grid">
            <MetricCard
              label="Total registrations"
              value={summaryQuery.data.registration_summary.total_registrations}
            />
            <MetricCard
              label="Confirmed"
              value={summaryQuery.data.registration_summary.confirmed}
            />
            <MetricCard
              label="Cancelled"
              value={summaryQuery.data.registration_summary.cancelled}
            />
            <MetricCard
              label="Waitlisted"
              value={summaryQuery.data.registration_summary.waitlisted}
            />
            <MetricCard
              label="Refunded"
              value={summaryQuery.data.registration_summary.refunded}
            />
            <MetricCard
              label="Checked-in rate"
              value={summaryQuery.data.registration_summary.check_in_rate}
            />
          </section>

          <section className="metric-grid">
            <MetricCard
              label="Gross revenue"
              value={formatCurrency(
                summaryQuery.data.revenue.gross_revenue,
                summaryQuery.data.revenue.currency,
              )}
            />
            <MetricCard
              label="Net revenue"
              value={formatCurrency(
                summaryQuery.data.revenue.net_revenue,
                summaryQuery.data.revenue.currency,
              )}
            />
            <MetricCard
              label="Total refunded"
              value={formatCurrency(
                summaryQuery.data.revenue.total_refunded,
                summaryQuery.data.revenue.currency,
              )}
            />
            <MetricCard
              label="Average ticket price"
              value={formatCurrency(
                summaryQuery.data.revenue.average_ticket_price,
                summaryQuery.data.revenue.currency,
              )}
            />
            <MetricCard
              label="Single registrations"
              value={summaryQuery.data.batch_vs_single.single_registration_count}
            />
            <MetricCard
              label="Average batch size"
              value={summaryQuery.data.batch_vs_single.average_batch_size.toFixed(1)}
            />
          </section>

          <section className="event-detail-grid">
            <article className="detail-card">
              <h2 className="detail-card__title">Scope summary</h2>
              <dl className="detail-list">
                <div>
                  <dt>Events in scope</dt>
                  <dd>
                    {summaryQuery.data.events.length > 0
                      ? summaryQuery.data.events.map((event) => event.title).join(", ")
                      : "All events"}
                  </dd>
                </div>
                <div>
                  <dt>Date from</dt>
                  <dd>{summaryQuery.data.date_range.from ? formatDate(summaryQuery.data.date_range.from) : "Not limited"}</dd>
                </div>
                <div>
                  <dt>Date to</dt>
                  <dd>{summaryQuery.data.date_range.to ? formatDate(summaryQuery.data.date_range.to) : "Not limited"}</dd>
                </div>
                <div>
                  <dt>Peak registration day</dt>
                  <dd>
                    {summaryQuery.data.registration_trends.peak_registration_day
                      ? formatDate(summaryQuery.data.registration_trends.peak_registration_day)
                      : "No registrations"}
                  </dd>
                </div>
              </dl>
            </article>

            <article className="detail-card">
              <h2 className="detail-card__title">Batch vs single mix</h2>
              <dl className="detail-list">
                <div>
                  <dt>Single registrations</dt>
                  <dd>{summaryQuery.data.batch_vs_single.single_registration_count}</dd>
                </div>
                <div>
                  <dt>Batch registrations</dt>
                  <dd>{summaryQuery.data.batch_vs_single.batch_registration_count}</dd>
                </div>
                <div>
                  <dt>Batch submissions</dt>
                  <dd>{summaryQuery.data.batch_vs_single.batch_submission_count}</dd>
                </div>
                <div>
                  <dt>Average batch size</dt>
                  <dd>{summaryQuery.data.batch_vs_single.average_batch_size.toFixed(1)}</dd>
                </div>
              </dl>
            </article>
          </section>

          {summaryQuery.data.revenue.revenue_by_event.length > 0 ? (
            <section className="panel">
              <div className="section-header">
                <div>
                  <h2 className="section-title">Revenue by event</h2>
                  <p className="section-note">
                    Gross revenue totals as returned by the analytics summary endpoint.
                  </p>
                </div>
              </div>

              <div className="table-wrap">
                <table className="data-table">
                  <caption className="sr-only">
                    Revenue by event for the current analytics scope.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Event</th>
                      <th scope="col">Gross revenue</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summaryQuery.data.revenue.revenue_by_event.map((eventRevenue) => (
                      <tr key={eventRevenue.event_id}>
                        <td>
                          <div className="table-cell-stack">
                            <strong>{eventRevenue.title}</strong>
                            <span>{eventRevenue.event_id}</span>
                          </div>
                        </td>
                        <td>
                          {formatCurrency(
                            eventRevenue.gross_revenue,
                            summaryQuery.data.revenue.currency,
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          <section className="panel">
            <div className="section-header">
              <div>
                <h2 className="section-title">Daily registration trend</h2>
                <p className="section-note">
                  Daily counts and cumulative totals from the backend analytics summary.
                </p>
              </div>
            </div>

            {summaryQuery.data.registration_trends.daily.length === 0 ? (
              <EmptyState
                title="No trend data is available"
                description="The current analytics scope has no registration trend points to display."
              />
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <caption className="sr-only">
                    Daily registration trend for the current analytics scope, including daily counts and cumulative totals.
                  </caption>
                  <thead>
                    <tr>
                      <th scope="col">Date</th>
                      <th scope="col">Registrations</th>
                      <th scope="col">Cumulative total</th>
                    </tr>
                  </thead>
                  <tbody>
                    {summaryQuery.data.registration_trends.daily.map((point) => (
                      <tr key={point.date}>
                        <td>{formatDate(point.date)}</td>
                        <td>{point.count}</td>
                        <td>{point.cumulative}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {summaryQuery.data.capacity ? (
            <section className="panel">
              <div className="section-header">
                <div>
                  <h2 className="section-title">Capacity snapshot</h2>
                  <p className="section-note">
                    Capacity appears only when the backend can calculate it for the current scope.
                  </p>
                </div>
              </div>
              <div className="metric-grid">
                <MetricCard label="Capacity" value={summaryQuery.data.capacity.capacity} />
                <MetricCard label="Slots filled" value={summaryQuery.data.capacity.slots_filled} />
                <MetricCard label="Slots remaining" value={summaryQuery.data.capacity.slots_remaining} />
                <MetricCard label="Waitlist length" value={summaryQuery.data.capacity.waitlist_length} />
                <MetricCard label="Fill rate" value={summaryQuery.data.capacity.fill_rate} />
                <MetricCard
                  label="Capacity overrides"
                  value={summaryQuery.data.capacity.capacity_override_count}
                />
              </div>
            </section>
          ) : null}
        </>
      )}
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number | string }) {
  return (
    <article className="metric-card">
      <p className="metric-card__label">{label}</p>
      <p className="metric-card__value">{value}</p>
    </article>
  );
}

function parseAnalyticsSearchParams(searchParams: URLSearchParams): AdminAnalyticsSummaryParams {
  const filters: AdminAnalyticsSummaryParams = {};
  const eventIds = uniqueNonEmpty(searchParams.getAll("event_ids"));
  if (eventIds.length > 0) {
    filters.event_ids = eventIds;
  }

  const dateFrom = searchParams.get("date_from")?.trim();
  if (dateFrom) {
    filters.date_from = dateFrom;
  }

  const dateTo = searchParams.get("date_to")?.trim();
  if (dateTo) {
    filters.date_to = dateTo;
  }

  return filters;
}

function uniqueNonEmpty(values: string[]): string[] {
  return Array.from(new Set(values.map((value) => value.trim()).filter(Boolean)));
}

function formatCurrency(amount: number, currency: string): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(amount);
}

function triggerBrowserDownload(blob: Blob, filename: string) {
  const objectUrl = window.URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = objectUrl;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  window.URL.revokeObjectURL(objectUrl);
}
