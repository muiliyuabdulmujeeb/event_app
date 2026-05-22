import { useEffect, useId, useRef } from "react";

import { formatDateTime } from "../lib/date";
import type { UserNotification } from "../types/registrations";

type NotificationQueueProps = {
  notifications: UserNotification[];
  pendingNotificationId: string | null;
  errorMessage: string | null;
  onDismiss: (notificationId: string) => void;
};

export function NotificationQueue({
  notifications,
  pendingNotificationId,
  errorMessage,
  onDismiss,
}: NotificationQueueProps) {
  const activeNotification = notifications[0];
  const dismissButtonRef = useRef<HTMLButtonElement | null>(null);
  const titleId = useId();
  const descriptionId = useId();

  useEffect(() => {
    if (!activeNotification) {
      return;
    }

    dismissButtonRef.current?.focus();
  }, [activeNotification?.id]);

  if (!activeNotification) {
    return null;
  }

  const isPending = pendingNotificationId === activeNotification.id;
  const remainingCountLabel =
    notifications.length === 1
      ? "This is the last unread update for this registration."
      : `${notifications.length} unread updates remain, including this one.`;

  return (
    <div className="notification-queue" role="presentation">
      <div className="notification-queue__backdrop" />
      <section
        className="notification-queue__dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
      >
        <p className="eyebrow">Notification</p>
        <h2 className="notification-queue__title" id={titleId}>
          {activeNotification.title}
        </h2>
        <p className="notification-queue__meta">{formatDateTime(activeNotification.created_at)}</p>
        <p className="notification-queue__body" id={descriptionId}>
          {activeNotification.body}
        </p>
        <p className="notification-queue__progress">{remainingCountLabel}</p>

        {errorMessage ? (
          <div className="form-alert" role="alert">
            {errorMessage}
          </div>
        ) : null}

        <div className="panel__actions">
          <button
            ref={dismissButtonRef}
            type="button"
            className="button-link button-link--primary"
            onClick={() => onDismiss(activeNotification.id)}
            disabled={isPending}
          >
            {isPending
              ? "Updating..."
              : notifications.length > 1
                ? "Acknowledge and continue"
                : "Acknowledge"}
          </button>
        </div>
      </section>
    </div>
  );
}
