import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getPublicEventDetail } from "../api/publicEvents";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { EventFieldType, PublicEventDetail } from "../types/events";

export function EventDetailPage() {
  const { eventId } = useParams<{ eventId: string }>();

  if (!eventId) {
    return <ErrorState title="Event unavailable" message="The event identifier is missing from the current route." />;
  }

  const eventQuery = useQuery<PublicEventDetail, ApiError>({
    queryKey: queryKeys.publicEvents.detail(eventId),
    queryFn: ({ signal }) => getPublicEventDetail(eventId, signal),
  });

  if (eventQuery.isPending) {
    return <LoadingState label="Loading event details…" />;
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
          eyebrow={event.is_free ? "Free event" : "Paid event"}
          title={event.title}
          description={event.description}
        />

        <div className="event-detail-grid">
          <article className="detail-card">
            <h2 className="detail-card__title">Event summary</h2>
            <dl className="detail-list">
              <div>
                <dt>Date</dt>
                <dd>{formatDateTime(event.event_date)}</dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{event.location}</dd>
              </div>
              <div>
                <dt>Price</dt>
                <dd>{event.is_free ? "Free" : formatPrice(event.price)}</dd>
              </div>
              <div>
                <dt>Capacity</dt>
                <dd>{event.capacity ?? "Unlimited"}</dd>
              </div>
            </dl>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Registration options</h2>
            <p className="detail-card__text">
              Use the event-specific registration routes below when you are ready. The submission flows are connected in the next frontend phases.
            </p>
            <div className="panel__actions">
              <Link to={`/events/${event.id}/register`} className="button-link button-link--primary">
                Single registration
              </Link>
              <Link to={`/events/${event.id}/register/batch`} className="button-link">
                Batch registration
              </Link>
            </div>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Required information preview</h2>
          <p className="section-note">
            These fields come directly from the event configuration and will drive the registration forms in the next phases.
          </p>
        </div>

        {event.custom_fields.length === 0 ? (
          <EmptyState
            title="No custom fields for this event"
            description="This event currently uses only the standard registration information."
          />
        ) : (
          <ol className="custom-field-list">
            {event.custom_fields.map((field) => (
              <li key={field.id} className="custom-field-item">
                <div className="custom-field-item__main">
                  <h3 className="custom-field-item__title">{field.label}</h3>
                  <p className="custom-field-item__meta">
                    {formatFieldType(field.field_type)} field
                    {field.is_required ? " · Required" : " · Optional"}
                  </p>
                </div>
                <span className={field.is_required ? "status-pill status-pill--success" : "status-pill status-pill--neutral"}>
                  {field.is_required ? "Required" : "Optional"}
                </span>
              </li>
            ))}
          </ol>
        )}
      </section>
    </div>
  );
}

function formatFieldType(fieldType: EventFieldType): string {
  switch (fieldType) {
    case "text":
      return "Text";
    case "number":
      return "Number";
    case "date":
      return "Date";
    case "phone":
      return "Phone";
    case "email":
      return "Email";
  }
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
}
