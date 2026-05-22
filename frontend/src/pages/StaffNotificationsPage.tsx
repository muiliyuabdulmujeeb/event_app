import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { listStaffNotifications, markStaffNotificationRead } from "../api/staff";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { StaffNotification, StaffNotificationListResponse } from "../types/staff";

export function StaffNotificationsPage() {
  const queryClient = useQueryClient();

  const notificationsQuery = useQuery<StaffNotificationListResponse, ApiError>({
    queryKey: queryKeys.staff.notifications,
    queryFn: ({ signal }) => listStaffNotifications(signal),
  });

  const markReadMutation = useMutation({
    mutationFn: markStaffNotificationRead,
    onSuccess: (response) => {
      queryClient.setQueryData<StaffNotificationListResponse | undefined>(
        queryKeys.staff.notifications,
        (current) => {
          if (!current) {
            return current;
          }

          const notifications = current.notifications.filter(
            (notification) => notification.id !== response.id,
          );

          return {
            notifications,
            total: notifications.length,
          };
        },
      );
    },
  });

  const pendingNotificationId = markReadMutation.isPending
    ? markReadMutation.variables ?? null
    : null;

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Staff"
          title="Unread notifications"
          description="This page shows only unread staff notifications, matching the backend endpoint exactly."
        />
      </section>

      {notificationsQuery.isPending ? (
        <LoadingState label="Loading unread notifications..." />
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
          description="You have no unread staff notifications at the moment."
        />
      ) : null}

      {notificationsQuery.isSuccess && notificationsQuery.data.notifications.length > 0 ? (
        <section className="panel">
          <div className="section-header">
            <h2 className="section-title">Unread items</h2>
            <p className="section-note">
              Marking an item as read removes it from this unread-only list.
            </p>
          </div>

          {markReadMutation.isError ? (
            <div className="form-alert" role="alert">
              {markReadMutation.error.message}
            </div>
          ) : null}

          <div className="notification-list">
            {notificationsQuery.data.notifications.map((notification) => (
              <StaffNotificationCard
                key={notification.id}
                notification={notification}
                pending={pendingNotificationId === notification.id}
                onMarkRead={() => markReadMutation.mutate(notification.id)}
              />
            ))}
          </div>
        </section>
      ) : null}
    </div>
  );
}

function StaffNotificationCard({
  notification,
  pending,
  onMarkRead,
}: {
  notification: StaffNotification;
  pending: boolean;
  onMarkRead: () => void;
}) {
  return (
    <article className="notification-card">
      <div className="notification-card__content">
        <h3 className="notification-card__title">{notification.title}</h3>
        <p className="notification-card__meta">{formatDateTime(notification.created_at)}</p>
        <p className="notification-card__body">{notification.body}</p>
      </div>
      <div className="notification-card__actions">
        <button
          type="button"
          className="button-link button-link--primary"
          onClick={onMarkRead}
          disabled={pending}
        >
          {pending ? "Updating..." : "Mark as read"}
        </button>
      </div>
    </article>
  );
}
