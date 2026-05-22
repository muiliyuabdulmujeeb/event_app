import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listAdminEvents } from "../api/adminEvents";
import { listStaffNotifications } from "../api/staff";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { UnreadNotificationPreviewPanel } from "../components/UnreadNotificationPreviewPanel";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { AdminEventListResponse, AdminEventSummary } from "../types/adminEvents";
import type { StaffNotificationListResponse } from "../types/staff";

export function AdminDashboardPage() {
  const eventsQuery = useQuery<AdminEventListResponse, ApiError>({
    queryKey: queryKeys.adminEvents.all,
    queryFn: ({ signal }) => listAdminEvents(signal),
  });
  const notificationsQuery = useQuery<StaffNotificationListResponse, ApiError>({
    queryKey: queryKeys.staff.notifications,
    queryFn: ({ signal }) => listStaffNotifications(signal),
  });

  const metrics = useMemo(() => {
    if (!eventsQuery.data) {
      return null;
    }

    const totals = {
      totalEvents: eventsQuery.data.total,
      draftEvents: 0,
      publishedEvents: 0,
      completedEvents: 0,
      cancelledEvents: 0,
      totalRegistrations: 0,
      totalConfirmed: 0,
    };

    for (const event of eventsQuery.data.events) {
      totals.totalRegistrations += event.registration_count;
      totals.totalConfirmed += event.confirmed_count;

      if (event.state === "draft") {
        totals.draftEvents += 1;
      } else if (event.state === "published") {
        totals.publishedEvents += 1;
      } else if (event.state === "completed") {
        totals.completedEvents += 1;
      } else if (event.state === "cancelled") {
        totals.cancelledEvents += 1;
      }
    }

    return totals;
  }, [eventsQuery.data]);
  const shouldShowNotificationPanel =
    notificationsQuery.isPending ||
    notificationsQuery.isError ||
    (notificationsQuery.isSuccess && notificationsQuery.data.total > 0);

  if (eventsQuery.isPending) {
    return <LoadingState label="Loading admin dashboard..." />;
  }

  if (eventsQuery.isError) {
    return (
      <ErrorState
        title="Could not load the admin dashboard"
        message={eventsQuery.error.message}
      />
    );
  }

  if (eventsQuery.data.total === 0 || !metrics) {
    return (
      <div className="page-stack">
        <section className="panel">
          <PageHeader
            eyebrow="Admin"
            title="Dashboard"
            description="This dashboard is composed from the current event inventory. Create the first event to start managing registrations and capacity."
          />
          <div className="panel__actions">
            <Link to="/admin/events/new" className="button-link button-link--primary">
              Create the first event
            </Link>
          </div>
        </section>

        {shouldShowNotificationPanel ? (
          <UnreadNotificationPreviewPanel
            title="Unread notifications"
            description="This panel uses the shared unread staff/admin notifications endpoint for the current account. The detailed unread inbox currently lives on the staff notifications route."
            notifications={notificationsQuery.data?.notifications ?? []}
            total={notificationsQuery.data?.total ?? 0}
            isPending={notificationsQuery.isPending}
            errorMessage={notificationsQuery.isError ? notificationsQuery.error.message : null}
            emptyMessage="There are no unread notifications for this account right now."
            actions={[
              { to: "/staff/notifications", label: "Open unread inbox", primary: true },
              { to: "/admin/notifications", label: "Send notification" },
            ]}
          />
        ) : null}

        <EmptyState
          title="No events created yet"
          description="Once events exist, this dashboard will summarize states, registrations, and recent updates using the live admin event list."
        />
      </div>
    );
  }

  const recentEvents = eventsQuery.data.events.slice(0, 5);

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Dashboard"
          description="Review the current event inventory, monitor registration activity, and jump directly into event creation or maintenance."
        />
        <div className="panel__actions">
          <Link to="/admin/events/new" className="button-link button-link--primary">
            Create event
          </Link>
          <Link to="/admin/events" className="button-link">
            Manage events
          </Link>
        </div>
      </section>

      {shouldShowNotificationPanel ? (
        <UnreadNotificationPreviewPanel
          title="Unread notifications"
          description="This panel uses the shared unread staff/admin notifications endpoint for the current account. The detailed unread inbox currently lives on the staff notifications route."
          notifications={notificationsQuery.data?.notifications ?? []}
          total={notificationsQuery.data?.total ?? 0}
          isPending={notificationsQuery.isPending}
          errorMessage={notificationsQuery.isError ? notificationsQuery.error.message : null}
          emptyMessage="There are no unread notifications for this account right now."
          actions={[
            { to: "/staff/notifications", label: "Open unread inbox", primary: true },
            { to: "/admin/notifications", label: "Send notification" },
          ]}
        />
      ) : null}

      <section className="metric-grid">
        <MetricCard label="Total events" value={metrics.totalEvents} />
        <MetricCard label="Published events" value={metrics.publishedEvents} />
        <MetricCard label="Total registrations" value={metrics.totalRegistrations} />
        <MetricCard label="Confirmed registrations" value={metrics.totalConfirmed} />
        <MetricCard label="Draft events" value={metrics.draftEvents} />
        <MetricCard label="Completed or cancelled" value={metrics.completedEvents + metrics.cancelledEvents} />
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Recent events</h2>
            <p className="section-note">
              Events are shown in the order returned by the backend event list.
            </p>
          </div>
          <Link to="/admin/events" className="button-link">
            View all events
          </Link>
        </div>

        <div className="result-list">
          {recentEvents.map((event) => (
            <article className="result-card" key={event.id}>
              <div className="result-card__header">
                <div>
                  <h3 className="result-card__title">{event.title}</h3>
                  <p className="result-card__meta">
                    {formatDateTime(event.event_date)} | {event.location}
                  </p>
                </div>
                <div className="panel__actions">
                  <span className="status-pill">{formatEventState(event.state)}</span>
                  <Link to={`/admin/events/${event.id}/edit`} className="button-link">
                    Edit event
                  </Link>
                </div>
              </div>

              <div className="result-card__grid">
                <SummaryBlock label="Pricing" value={event.is_free ? "Free" : formatPrice(event.price)} />
                <SummaryBlock label="Capacity" value={event.capacity ?? "Unlimited"} />
                <SummaryBlock label="Slots remaining" value={event.slots_remaining ?? "Unlimited"} />
                <SummaryBlock label="Registrations" value={`${event.registration_count} total / ${event.confirmed_count} confirmed`} />
              </div>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function MetricCard({ label, value }: { label: string; value: number }) {
  return (
    <article className="metric-card">
      <p className="metric-card__label">{label}</p>
      <p className="metric-card__value">{value}</p>
    </article>
  );
}

function SummaryBlock({ label, value }: { label: string; value: number | string }) {
  return (
    <article className="detail-card detail-card--compact">
      <h4 className="detail-section__title">{label}</h4>
      <p className="detail-card__text detail-card__text--strong">{value}</p>
    </article>
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

function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
}
