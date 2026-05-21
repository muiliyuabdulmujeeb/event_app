import { useDeferredValue } from "react";
import { useForm, useWatch } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { z } from "zod";

import { listPublicEvents } from "../api/publicEvents";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { PublicEventListResponse, PublicEventSummary } from "../types/events";

const eventFiltersSchema = z.object({
  search: z.string().max(255).default(""),
  pricing: z.enum(["all", "free", "paid"]).default("all"),
});

type EventFilters = z.infer<typeof eventFiltersSchema>;

export function EventListPage() {
  const form = useForm<EventFilters>({
    resolver: zodResolver(eventFiltersSchema),
    defaultValues: {
      search: "",
      pricing: "all",
    },
  });

  const searchValue = useWatch({ control: form.control, name: "search" }) ?? "";
  const pricingValue = useWatch({ control: form.control, name: "pricing" }) ?? "all";
  const deferredSearchValue = useDeferredValue(searchValue);

  const normalizedSearch = deferredSearchValue.trim() || undefined;
  const isFree =
    pricingValue === "all" ? null : pricingValue === "free";

  const eventsQuery = useQuery<PublicEventListResponse, ApiError>({
    queryKey: queryKeys.publicEvents.list({
      search: normalizedSearch,
      isFree,
    }),
    queryFn: ({ signal }) =>
      listPublicEvents(
        {
          search: normalizedSearch,
          isFree,
        },
        signal,
      ),
  });

  const isFiltering = Boolean(searchValue.trim()) || pricingValue !== "all";

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Public"
          title="Browse events"
          description="Discover published events, review the details that matter, and choose how you want to register."
        />

        <form className="filters-form" onSubmit={(event) => event.preventDefault()}>
          <div className="form-field filters-form__search">
            <label className="form-label" htmlFor="event-search">
              Search events
            </label>
            <input
              id="event-search"
              type="search"
              autoComplete="off"
              placeholder="Search by title, description, or location"
              className="form-input"
              {...form.register("search")}
            />
          </div>

          <div className="form-field filters-form__select">
            <label className="form-label" htmlFor="event-pricing">
              Pricing
            </label>
            <select id="event-pricing" className="form-input" {...form.register("pricing")}>
              <option value="all">All events</option>
              <option value="free">Free only</option>
              <option value="paid">Paid only</option>
            </select>
          </div>
        </form>
      </section>

      {eventsQuery.isPending ? <LoadingState label="Loading published events…" /> : null}

      {eventsQuery.isError ? (
        <ErrorState
          title="Could not load events"
          message={eventsQuery.error.message}
        />
      ) : null}

      {eventsQuery.isSuccess && eventsQuery.data.total === 0 ? (
        <EmptyState
          title={isFiltering ? "No events matched those filters" : "No published events are available yet"}
          description={
            isFiltering
              ? "Try clearing the search term or switching the pricing filter."
              : "Published events will appear here once they are available."
          }
        />
      ) : null}

      {eventsQuery.isSuccess && eventsQuery.data.events.length > 0 ? (
        <section aria-live="polite" className="events-section">
          <div className="events-section__header">
            <h2 className="section-title">
              {eventsQuery.data.total === 1 ? "1 event" : `${eventsQuery.data.total} events`}
            </h2>
            {eventsQuery.isFetching ? <p className="section-note">Updating results…</p> : null}
          </div>

          <div className="event-grid">
            {eventsQuery.data.events.map((event) => (
              <article key={event.id} className="event-card">
                <div className="event-card__body">
                  <div className="event-card__header">
                    <div>
                      <h3 className="event-card__title">
                        <Link to={`/events/${event.id}`} className="event-card__title-link">
                          {event.title}
                        </Link>
                      </h3>
                      <p className="event-card__location">{event.location}</p>
                    </div>
                    <PriceBadge event={event} />
                  </div>

                  <dl className="event-meta">
                    <div>
                      <dt>Date</dt>
                      <dd>{formatDateTime(event.event_date)}</dd>
                    </div>
                    <div>
                      <dt>Capacity</dt>
                      <dd>{event.capacity ?? "Unlimited"}</dd>
                    </div>
                  </dl>

                  <p className="event-card__description">{event.description}</p>
                </div>

                <div className="event-card__actions">
                  <Link to={`/events/${event.id}`} className="button-link button-link--primary">
                    View details
                  </Link>
                  <Link to={`/events/${event.id}/register`} className="button-link">
                    Register
                  </Link>
                </div>
              </article>
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function PriceBadge({ event }: { event: Pick<PublicEventSummary, "is_free" | "price"> }) {
  if (event.is_free) {
    return <span className="status-pill status-pill--success">Free</span>;
  }

  return <span className="status-pill">Paid · {formatPrice(event.price)}</span>;
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
}
