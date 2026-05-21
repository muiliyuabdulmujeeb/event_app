import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listStaffNotifications } from "../api/staff";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import { useAuthSession } from "../lib/session";
import type { StaffNotificationListResponse } from "../types/staff";

export function StaffDashboardPage() {
  const session = useAuthSession();
  const notificationsQuery = useQuery<StaffNotificationListResponse, ApiError>({
    queryKey: queryKeys.staff.notifications,
    queryFn: ({ signal }) => listStaffNotifications(signal),
  });

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Staff"
          title="Operations dashboard"
          description="Use this workspace to search registrations, process check-ins, and review unread staff notifications."
        />

        <div className="metric-grid">
          <article className="detail-card">
            <h2 className="detail-card__title">Current session</h2>
            <dl className="detail-list">
              <div>
                <dt>Access level</dt>
                <dd>{session?.role === "admin" ? "Admin" : "Staff"}</dd>
              </div>
              <div>
                <dt>Unread notifications</dt>
                <dd>
                  {notificationsQuery.isSuccess ? notificationsQuery.data.total : "Loading..."}
                </dd>
              </div>
            </dl>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Quick actions</h2>
            <div className="panel__actions">
              <Link to="/staff/registrations" className="button-link button-link--primary">
                Search registrations
              </Link>
              <Link to="/staff/notifications" className="button-link">
                View notifications
              </Link>
            </div>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Unread notifications</h2>
          <p className="section-note">
            This dashboard uses the same unread-notification endpoint as the dedicated staff notifications page.
          </p>
        </div>

        {notificationsQuery.isPending ? (
          <LoadingState label="Loading unread staff notifications..." />
        ) : null}

        {notificationsQuery.isError ? (
          <ErrorState
            title="Could not load unread notifications"
            message={notificationsQuery.error.message}
          />
        ) : null}

        {notificationsQuery.isSuccess && notificationsQuery.data.notifications.length === 0 ? (
          <EmptyState
            title="No unread notifications"
            description="You are fully caught up right now."
          />
        ) : null}

        {notificationsQuery.isSuccess && notificationsQuery.data.notifications.length > 0 ? (
          <div className="notification-list">
            {notificationsQuery.data.notifications.slice(0, 3).map((notification) => (
              <article className="notification-card" key={notification.id}>
                <div className="notification-card__content">
                  <h3 className="notification-card__title">{notification.title}</h3>
                  <p className="notification-card__meta">
                    {formatDateTime(notification.created_at)}
                  </p>
                  <p className="notification-card__body">{notification.body}</p>
                </div>
              </article>
            ))}
          </div>
        ) : null}

        {notificationsQuery.isSuccess && notificationsQuery.data.notifications.length > 3 ? (
          <div className="panel__actions">
            <Link to="/staff/notifications" className="button-link">
              View all unread notifications
            </Link>
          </div>
        ) : null}
      </section>
    </div>
  );
}
