from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.security import utc_now
from app.core.exceptions import (
    EventNotFoundError,
    RegistrationNotFoundError,
    UserNotificationNotFoundError,
)
from app.models.event import Event, OverflowRule
from app.models.payment import Payment
from app.models.refund_request import RefundRequest
from app.models.registration import Registration, RegistrationState
from app.repositories.notification_repository import NotificationRepository
from app.repositories.registration_repository import RegistrationRepository
from app.schemas.email import EmailMessage
from app.schemas.notification import (
    AdminNotificationCreateRequest,
    AdminNotificationDispatchResponse,
    AdminNotificationType,
    NotificationMethod,
    RegistrationLookupCustomFieldValueResponse,
    RegistrationLookupEventResponse,
    RegistrationLookupPaymentResponse,
    RegistrationLookupPromotionOfferResponse,
    RegistrationLookupRefundRequestResponse,
    RegistrationLookupRegistrationResponse,
    RegistrationLookupResponse,
    UserNotificationResponse,
    UserNotificationSeenResponse,
)
from app.services.email_templates import build_ticket_email_message
from app.models.waitlist_promotion_offer import WaitlistPromotionOffer, WaitlistPromotionOfferStatus


DEFAULT_EVENT_CANCELLATION_TITLE = "Event Cancelled"
DEFAULT_PRICE_CHANGE_TITLE = "Price Updated"
DEFAULT_REFUND_PROCESSED_TITLE = "Refund Processed"
DEFAULT_MANUAL_PAYMENT_REVIEW_TITLE = "Manual Payment Review Required"
DEFAULT_PAYMENT_RETRY_TITLE = "Payment Retry Available"


@dataclass(frozen=True)
class NotificationDispatchResult:
    user_notifications_created: int = 0
    staff_notifications_created: int = 0
    email_messages: list[EmailMessage] = field(default_factory=list)


@dataclass(frozen=True)
class AdminNotificationServiceResult:
    response: AdminNotificationDispatchResponse
    email_messages: list[EmailMessage] = field(default_factory=list)


@dataclass
class NotificationService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.notification_repository = NotificationRepository(self.session)
        self.registration_repository = RegistrationRepository(self.session)

    async def lookup_registration(self, reg_id: str) -> RegistrationLookupResponse:
        registration = await self.registration_repository.get_registration_by_reg_id(reg_id)
        if registration is None:
            raise RegistrationNotFoundError("No registration found for the provided reg_id.")

        notifications = await self.notification_repository.list_unseen_user_notifications(reg_id)
        return RegistrationLookupResponse(
            registration=self._build_lookup_registration(registration),
            event=RegistrationLookupEventResponse(
                id=registration.event.id,
                title=registration.event.title,
                event_date=registration.event.event_date,
                location=registration.event.location,
                is_free=registration.event.is_free,
                state=registration.event.state,
            ),
            payment=(
                RegistrationLookupPaymentResponse(
                    status=registration.payment.status,
                    amount_paid=registration.payment.amount,
                    currency=registration.payment.currency,
                    paid_at=registration.payment.paid_at,
                )
                if registration.payment is not None
                else None
            ),
            promotion_offer=self._build_lookup_promotion_offer(registration.waitlist_promotion_offer),
            refund_request=self._build_lookup_refund_request(registration.refund_requests[0] if registration.refund_requests else None),
            notifications=[
                UserNotificationResponse(
                    id=notification.id,
                    title=notification.title,
                    body=notification.body,
                    is_seen=notification.is_seen,
                    created_at=notification.created_at,
                )
                for notification in notifications
            ],
        )

    async def mark_user_notification_seen(self, notification_id: str) -> UserNotificationSeenResponse:
        notification = await self.notification_repository.get_user_notification(notification_id)
        if notification is None:
            raise UserNotificationNotFoundError("User notification not found.")

        notification.is_seen = True
        await self.session.flush()
        return UserNotificationSeenResponse(id=notification.id, is_seen=notification.is_seen)

    async def dispatch_admin_notification(
        self,
        payload: AdminNotificationCreateRequest,
    ) -> AdminNotificationServiceResult:
        if payload.notification_type == AdminNotificationType.REFUND:
            registration = await self.registration_repository.get_registration_by_reg_id(payload.reg_id or "")
            if registration is None:
                raise RegistrationNotFoundError("No registration found for the provided reg_id.")
            dispatch_result = await self.dispatch_refund_notification(
                registration=registration,
                method=payload.notification_method,
                title=payload.title or DEFAULT_REFUND_PROCESSED_TITLE,
                body=payload.body,
            )
        else:
            event_id = payload.event_id or ""
            event = await self.registration_repository.get_event_with_fields(event_id)
            if event is None:
                raise EventNotFoundError("Event not found.")
            if payload.notification_type == AdminNotificationType.PRICE_CHANGE:
                dispatch_result = await self.dispatch_price_change_notifications(
                    event=event,
                    method=payload.notification_method,
                    body=payload.body,
                    title=payload.title or DEFAULT_PRICE_CHANGE_TITLE,
                )
            else:
                dispatch_result = await self.dispatch_event_cancellation_notifications(
                    event=event,
                    method=payload.notification_method,
                    body=payload.body,
                    title=payload.title or DEFAULT_EVENT_CANCELLATION_TITLE,
                    mutate_registration_states=False,
                )

        return AdminNotificationServiceResult(
            response=AdminNotificationDispatchResponse(
                notification_type=payload.notification_type,
                notification_method=payload.notification_method,
                user_notifications_created=dispatch_result.user_notifications_created,
                staff_notifications_created=dispatch_result.staff_notifications_created,
                email_recipients_count=sum(len(message.to) for message in dispatch_result.email_messages),
                message="Notification sent successfully.",
            ),
            email_messages=dispatch_result.email_messages,
        )

    async def dispatch_price_change_notifications(
        self,
        *,
        event: Event,
        method: NotificationMethod,
        body: str,
        title: str = DEFAULT_PRICE_CHANGE_TITLE,
    ) -> NotificationDispatchResult:
        confirmed_registrations = await self.registration_repository.list_registrations_for_event(
            event.id,
            states=[RegistrationState.CONFIRMED],
        )
        email_messages: list[EmailMessage] = []
        user_notifications_created = 0
        staff_notifications_created = 0

        if method == NotificationMethod.IN_APP:
            user_notifications_created = await self._create_user_notifications_for_registrations(
                registrations=confirmed_registrations,
                title=title,
                body=body,
            )
            staff_notifications_created = await self._create_staff_notifications_for_active_accounts(title=title, body=body)
        else:
            email_messages = self._build_bulk_event_email_messages(
                event=event,
                registrations=confirmed_registrations,
                subject=title,
                body=body,
                notification_type=AdminNotificationType.PRICE_CHANGE.value,
            )

        return NotificationDispatchResult(
            user_notifications_created=user_notifications_created,
            staff_notifications_created=staff_notifications_created,
            email_messages=email_messages,
        )

    async def dispatch_event_cancellation_notifications(
        self,
        *,
        event: Event,
        method: NotificationMethod,
        body: str,
        title: str = DEFAULT_EVENT_CANCELLATION_TITLE,
        mutate_registration_states: bool = True,
    ) -> NotificationDispatchResult:
        affected_registrations = await self.registration_repository.list_registrations_for_event(
            event.id,
            states=[RegistrationState.CONFIRMED, RegistrationState.PENDING_PAYMENT],
            for_update=mutate_registration_states,
        )
        confirmed_registrations = [
            registration
            for registration in affected_registrations
            if registration.state == RegistrationState.CONFIRMED
        ]

        if mutate_registration_states:
            for registration in affected_registrations:
                registration.state = RegistrationState.CANCELLED

        user_notifications_created = await self._create_user_notifications_for_registrations(
            registrations=confirmed_registrations,
            title=title,
            body=body,
        )
        staff_notifications_created = await self._create_staff_notifications_for_active_accounts(title=title, body=body)
        email_messages = []
        if method == NotificationMethod.EMAIL:
            email_messages = self._build_bulk_event_email_messages(
                event=event,
                registrations=confirmed_registrations,
                subject=title,
                body=body,
                notification_type=AdminNotificationType.EVENT_CANCELLATION.value,
            )

        await self.session.flush()
        return NotificationDispatchResult(
            user_notifications_created=user_notifications_created,
            staff_notifications_created=staff_notifications_created,
            email_messages=email_messages,
        )

    async def dispatch_refund_notification(
        self,
        *,
        registration: Registration,
        method: NotificationMethod,
        title: str,
        body: str,
    ) -> NotificationDispatchResult:
        if method == NotificationMethod.IN_APP:
            user_count = await self._create_user_notifications_for_registrations(
                registrations=[registration],
                title=title,
                body=body,
            )
            return NotificationDispatchResult(
                user_notifications_created=user_count,
                staff_notifications_created=0,
                email_messages=[],
            )

        return NotificationDispatchResult(
            user_notifications_created=0,
            staff_notifications_created=0,
            email_messages=[
                self._build_custom_email_message(
                    to=[registration.email],
                    subject=title,
                    body=body,
                    metadata={
                        "template": "admin_notification",
                        "notification_type": AdminNotificationType.REFUND.value,
                        "reg_id": registration.reg_id,
                    },
                )
            ],
        )

    async def promote_next_waitlisted_registration_if_needed(
        self,
        *,
        event: Event,
        released_from_confirmed: bool,
    ) -> list[EmailMessage]:
        return await self._promote_next_waitlisted_registration_if_needed(
            event=event,
            released_from_confirmed=released_from_confirmed,
        )

    async def notify_manual_payment_review(
        self,
        *,
        payment: Payment,
        paid_at: str | None = None,
    ) -> None:
        owner = payment.registration.reg_id if payment.registration is not None else payment.batch_id
        owner_label = "registration" if payment.registration is not None else "batch"
        paid_at_suffix = f" at {paid_at}" if paid_at is not None else ""
        body = (
            f"Payment reference {payment.payment_reference} reported success{paid_at_suffix} after the original "
            f"payment window had already been closed. Review the affected {owner_label} ({owner}) manually."
        )
        await self._create_staff_notifications_for_active_accounts(
            title=DEFAULT_MANUAL_PAYMENT_REVIEW_TITLE,
            body=body,
        )

    async def dispatch_payment_retry_notification(
        self,
        *,
        registration: Registration,
        title: str = DEFAULT_PAYMENT_RETRY_TITLE,
    ) -> NotificationDispatchResult:
        payment_action_url = (
            f"{self.settings.application_base_url.rstrip('/')}"
            f"/registrations/{registration.reg_id}/payments/initialize"
        )
        body = (
            "A new payment attempt is available for your registration. "
            f"Use this link to continue payment: {payment_action_url}"
        )
        user_notifications_created = await self._create_user_notifications_for_registrations(
            registrations=[registration],
            title=title,
            body=body,
        )
        email_message = self._build_custom_email_message(
            to=[registration.email],
            subject=title,
            body=body,
            metadata={
                "template": "payment_retry",
                "reg_id": registration.reg_id,
                "event_id": registration.event_id,
            },
        )
        return NotificationDispatchResult(
            user_notifications_created=user_notifications_created,
            staff_notifications_created=0,
            email_messages=[email_message],
        )

    async def _create_user_notifications_for_registrations(
        self,
        *,
        registrations: list[Registration],
        title: str,
        body: str,
    ) -> int:
        count = 0
        for registration in registrations:
            await self.notification_repository.create_user_notification(
                reg_id=registration.reg_id,
                title=title,
                body=body,
            )
            count += 1
        return count

    async def _create_staff_notifications_for_active_accounts(self, *, title: str, body: str) -> int:
        staff_accounts = await self.notification_repository.list_active_staff_accounts()
        for account in staff_accounts:
            await self.notification_repository.create_staff_notification(
                staff_id=account.id,
                title=title,
                body=body,
            )
        return len(staff_accounts)

    async def _promote_next_waitlisted_registration_if_needed(
        self,
        *,
        event: Event,
        released_from_confirmed: bool,
    ) -> list[EmailMessage]:
        if not released_from_confirmed or not event.is_free or event.overflow_rule != OverflowRule.WAITLIST:
            return []

        next_waitlisted = await self.registration_repository.get_next_waitlisted_registration(
            event.id,
            for_update=True,
        )
        if next_waitlisted is None:
            return []

        next_waitlisted.state = RegistrationState.CONFIRMED
        next_waitlisted.waitlist_position = None
        await self._resequence_waitlist(event.id)
        await self.session.flush()
        return [build_ticket_email_message(self.settings, event=event, registration=next_waitlisted)]

    async def _resequence_waitlist(self, event_id: str) -> None:
        waitlisted_registrations = await self.registration_repository.list_registrations_for_event(
            event_id,
            states=[RegistrationState.WAITLISTED],
            for_update=True,
        )
        for index, registration in enumerate(waitlisted_registrations, start=1):
            registration.waitlist_position = index

    def _build_lookup_registration(self, registration: Registration) -> RegistrationLookupRegistrationResponse:
        custom_field_values = [
            RegistrationLookupCustomFieldValueResponse(
                label=field_value.field_definition.label,
                value=field_value.value,
            )
            for field_value in sorted(
                registration.field_values,
                key=lambda item: item.field_definition.display_order,
            )
        ]
        return RegistrationLookupRegistrationResponse(
            reg_id=registration.reg_id,
            first_name=registration.first_name,
            last_name=registration.last_name,
            email=registration.email,
            state=registration.state,
            is_checked_in=registration.is_checked_in,
            checked_in_at=registration.checked_in_at,
            registered_at=registration.registered_at,
            is_batch=registration.batch_id is not None,
            was_waitlisted=registration.was_waitlisted,
            previous_waitlist_position=registration.previous_waitlist_position,
            cancellation_reason=registration.cancellation_reason,
            custom_field_values=custom_field_values,
        )

    def _build_lookup_promotion_offer(
        self,
        offer: WaitlistPromotionOffer | None,
    ) -> RegistrationLookupPromotionOfferResponse | None:
        if offer is None:
            return None

        payment_action_url: str | None = None
        if (
            offer.status in {WaitlistPromotionOfferStatus.OFFERED, WaitlistPromotionOfferStatus.PAYMENT_INITIALIZED}
            and offer.offer_expires_at > utc_now()
            and offer.registration.state == RegistrationState.PENDING_PAYMENT
        ):
            payment_action_url = (
                f"{self.settings.application_base_url.rstrip('/')}"
                f"/registrations/payment-offers/{offer.public_token}/initialize"
            )

        return RegistrationLookupPromotionOfferResponse(
            public_token=offer.public_token,
            status=offer.status,
            offer_expires_at=offer.offer_expires_at,
            payment_action_url=payment_action_url,
        )

    def _build_lookup_refund_request(
        self,
        refund_request: RefundRequest | None,
    ) -> RegistrationLookupRefundRequestResponse | None:
        if refund_request is None:
            return None
        return RegistrationLookupRefundRequestResponse(
            id=refund_request.id,
            status=refund_request.status,
            requested_at=refund_request.requested_at,
            processed_at=refund_request.processed_at,
        )

    def _build_bulk_event_email_messages(
        self,
        *,
        event: Event,
        registrations: list[Registration],
        subject: str,
        body: str,
        notification_type: str,
    ) -> list[EmailMessage]:
        return [
            self._build_custom_email_message(
                to=[registration.email],
                subject=subject,
                body=body,
                metadata={
                    "template": "admin_notification",
                    "notification_type": notification_type,
                    "reg_id": registration.reg_id,
                    "event_id": event.id,
                },
            )
            for registration in registrations
        ]

    def _build_custom_email_message(
        self,
        *,
        to: list[str],
        subject: str,
        body: str,
        metadata: dict[str, str],
    ) -> EmailMessage:
        html_body = "".join(f"<p>{line}</p>" for line in body.splitlines() if line.strip()) or f"<p>{body}</p>"
        return EmailMessage(
            from_email=self.settings.email_from,
            from_name=self.settings.email_from_name,
            to=to,
            subject=subject,
            text_body=body,
            html_body=html_body,
            metadata=metadata,
        )
