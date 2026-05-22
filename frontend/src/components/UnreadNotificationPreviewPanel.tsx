import { Link } from "react-router-dom";

import { LoadingState } from "./LoadingState";
import { formatDateTime } from "../lib/date";
import type { StaffNotification } from "../types/staff";

type NotificationPreviewAction = {
  to: string;
  label: string;
  primary?: boolean;
};

type UnreadNotificationPreviewPanelProps = {
  title: string;
  description: string;
  notifications: StaffNotification[];
  total: number;
  isPending: boolean;
  errorMessage: string | null;
  emptyMessage: string;
  actions?: NotificationPreviewAction[];
};

export function UnreadNotificationPreviewPanel({
  title,
  description,
  notifications,
  total,
  isPending,
  errorMessage,
  emptyMessage,
  actions = [],
}: UnreadNotificationPreviewPanelProps) {
  const visibleNotifications = notifications.slice(0, 3);

  return (
    <section className="panel">
      <div className="section-header">
        <div>
          <h2 className="section-title">{title}</h2>
          <p className="section-note">{description}</p>
        </div>
        {total > 0 ? <span className="status-pill">{total} unread</span> : null}
      </div>

      {isPending ? <LoadingState label="Loading unread notifications..." /> : null}

      {!isPending && errorMessage ? (
        <div className="form-alert" role="alert">
          {errorMessage}
        </div>
      ) : null}

      {!isPending && !errorMessage && total === 0 ? (
        <p className="detail-card__text">{emptyMessage}</p>
      ) : null}

      {!isPending && !errorMessage && visibleNotifications.length > 0 ? (
        <>
          <div className="notification-list">
            {visibleNotifications.map((notification) => (
              <article className="notification-card" key={notification.id}>
                <div className="notification-card__content">
                  <h3 className="notification-card__title">{notification.title}</h3>
                  <p className="notification-card__meta">{formatDateTime(notification.created_at)}</p>
                  <p className="notification-card__body">{notification.body}</p>
                </div>
              </article>
            ))}
          </div>

          {total > visibleNotifications.length ? (
            <p className="section-note">
              Showing {visibleNotifications.length} of {total} unread items.
            </p>
          ) : null}
        </>
      ) : null}

      {actions.length > 0 ? (
        <div className="panel__actions">
          {actions.map((action) => (
            <Link
              key={action.to}
              to={action.to}
              className={action.primary ? "button-link button-link--primary" : "button-link"}
            >
              {action.label}
            </Link>
          ))}
        </div>
      ) : null}
    </section>
  );
}
