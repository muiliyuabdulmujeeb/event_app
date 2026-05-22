import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { listStaffNotifications } from "../api/staff";
import { PageHeader } from "../components/PageHeader";
import { UnreadNotificationPreviewPanel } from "../components/UnreadNotificationPreviewPanel";
import { ApiError } from "../lib/apiError";
import { queryKeys } from "../lib/queryKeys";
import { useAuthSession } from "../lib/session";
import type { StaffNotificationListResponse } from "../types/staff";

export function StaffDashboardPage() {
  const session = useAuthSession();
  const notificationsQuery = useQuery<StaffNotificationListResponse, ApiError>({
    queryKey: queryKeys.staff.notifications,
    queryFn: ({ signal }) => listStaffNotifications(signal),
  });
  const shouldShowNotificationPanel =
    notificationsQuery.isPending ||
    notificationsQuery.isError ||
    (notificationsQuery.isSuccess && notificationsQuery.data.total > 0);

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

      {shouldShowNotificationPanel ? (
        <UnreadNotificationPreviewPanel
          title="Unread notifications waiting"
          description="Unread items are surfaced here when you sign in. Use the dedicated inbox to review and mark them as read."
          notifications={notificationsQuery.data?.notifications ?? []}
          total={notificationsQuery.data?.total ?? 0}
          isPending={notificationsQuery.isPending}
          errorMessage={notificationsQuery.isError ? notificationsQuery.error.message : null}
          emptyMessage="You are fully caught up right now."
          actions={[{ to: "/staff/notifications", label: "Open notification inbox", primary: true }]}
        />
      ) : null}
    </div>
  );
}
