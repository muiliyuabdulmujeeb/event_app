import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listAdminEvents } from "../api/adminEvents";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { AdminEventListResponse, AdminEventSummary } from "../types/adminEvents";

export function AdminEventsPage() {
  const eventsQuery = useQuery<AdminEventListResponse, ApiError>({
    queryKey: queryKeys.adminEvents.all,
    queryFn: ({ signal }) => listAdminEvents(signal),
  });

  if (eventsQuery.isPending) {
    return <LoadingState label="Loading admin events..." />;
  }

  if (eventsQuery.isError) {
    return (
      <ErrorState
        title="Could not load admin events"
        message={eventsQuery.error.message}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Events"
          description="Review the current event inventory, create new events, and open the edit workspace for state, pricing, and overflow-rule management."
        />
        <div className="panel__actions">
          <Link to="/admin/events/new" className="button-link button-link--primary">
            Create event
          </Link>
        </div>
      </section>

      {eventsQuery.data.total === 0 ? (
        <EmptyState
          title="No events created yet"
          description="Create an event to start managing published, draft, completed, and cancelled event records."
        />
      ) : (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2 className="section-title">Event inventory</h2>
              <p className="section-note">
                {eventsQuery.data.total} event{eventsQuery.data.total === 1 ? "" : "s"} loaded from the admin event list endpoint.
              </p>
            </div>
          </div>

          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Event</th>
                  <th scope="col">State</th>
                  <th scope="col">Pricing</th>
                  <th scope="col">Capacity</th>
                  <th scope="col">Registrations</th>
                  <th scope="col">Overrides</th>
                  <th scope="col">Updated</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {eventsQuery.data.events.map((event) => (
                  <tr key={event.id}>
                    <td>
                      <div className="table-cell-stack">
                        <strong>{event.title}</strong>
                        <span>{formatDateTime(event.event_date)}</span>
                        <span>{event.location}</span>
                        <span>Prefix: {event.prefix}</span>
                      </div>
                    </td>
                    <td>{formatEventState(event.state)}</td>
                    <td>{event.is_free ? "Free" : formatPrice(event.price)}</td>
                    <td>
                      <div className="table-cell-stack">
                        <span>{event.capacity ?? "Unlimited"} total</span>
                        <span>{event.slots_remaining ?? "Unlimited"} remaining</span>
                        <span>{formatOverflowRule(event.overflow_rule)}</span>
                      </div>
                    </td>
                    <td>
                      <div className="table-cell-stack">
                        <span>{event.registration_count} total</span>
                        <span>{event.confirmed_count} confirmed</span>
                      </div>
                    </td>
                    <td>{event.capacity_override_count}</td>
                    <td>{formatDateTime(event.updated_at)}</td>
                    <td>
                      <Link to={`/admin/events/${event.id}/edit`} className="button-link">
                        Edit event
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function formatEventState(state: AdminEventSummary["state"]): string {
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

function formatOverflowRule(rule: AdminEventSummary["overflow_rule"]): string {
  return rule === "waitlist" ? "Waitlist" : "Hard rejection";
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
}
