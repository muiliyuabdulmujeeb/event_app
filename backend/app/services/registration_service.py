from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, InvalidOperation
import re
import secrets
import string

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.core.exceptions import (
    DuplicateRegistrationError,
    EventConflictError,
    EventNotFoundError,
    RegistrationConflictError,
    RegistrationValidationError,
)
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.payment import Payment, PaymentGateway, PaymentStatus
from app.models.registration import Registration, RegistrationFieldValue, RegistrationState
from app.repositories.registration_repository import RegistrationRepository
from app.schemas.registration import (
    RegistrationCreateRequest,
    RegistrationCreateResponse,
    RegistrationServiceResult,
)


PHONE_REGEX = re.compile(r"^(?:\+[1-9]\d{7,14}|234\d{10}|0\d{10})$")
EMAIL_REGEX = re.compile(
    r"^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$"
)
REG_ID_SUFFIX_ALPHABET = string.ascii_uppercase + string.digits
REG_ID_SUFFIX_LENGTH = 6
REG_ID_RETRY_LIMIT = 3

ALLOWED_REGISTRATION_STATE_TRANSITIONS: dict[RegistrationState, set[RegistrationState]] = {
    RegistrationState.PENDING_PAYMENT: {
        RegistrationState.CONFIRMED,
        RegistrationState.FAILED,
        RegistrationState.CANCELLED,
    },
    RegistrationState.CONFIRMED: {
        RegistrationState.CANCELLED,
        RegistrationState.REFUND_REQUESTED,
    },
    RegistrationState.REFUND_REQUESTED: {RegistrationState.REFUNDED},
    RegistrationState.WAITLISTED: {
        RegistrationState.CONFIRMED,
        RegistrationState.CANCELLED,
    },
    RegistrationState.FAILED: set(),
    RegistrationState.CANCELLED: set(),
    RegistrationState.REFUNDED: set(),
}


@dataclass
class RegistrationService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.repository = RegistrationRepository(self.session)

    async def create_single_registration(
        self,
        event_id: str,
        payload: RegistrationCreateRequest,
    ) -> RegistrationServiceResult:
        event = await self.repository.get_event_with_fields(event_id)
        if event is None or event.state == EventState.DRAFT:
            raise EventNotFoundError("Event not found.")
        if event.state in {EventState.CANCELLED, EventState.COMPLETED}:
            raise RegistrationConflictError("This event is no longer accepting registrations.")

        await self._validate_duplicate_email(event.id, payload)

        submitted_values = self._normalize_custom_field_values(payload.custom_field_values)
        self._validate_custom_field_values(event, submitted_values)

        registration_state = await self._determine_initial_state(event)
        reg_id = await self._generate_reg_id(event)
        registration = Registration(
            event_id=event.id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=str(payload.email),
            reg_id=reg_id,
            state=registration_state,
            waitlist_position=(
                await self._next_waitlist_position(event.id)
                if registration_state == RegistrationState.WAITLISTED
                else None
            ),
        )

        registration.field_values = self._build_field_values(event, submitted_values)

        try:
            await self.repository.create_registration(registration)

            payment_url: str | None = None
            if registration_state == RegistrationState.PENDING_PAYMENT:
                payment_url = await self._create_pending_payment(registration, event)

            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise EventConflictError("The registration could not be saved because it conflicts with existing data.") from exc

        response = self._build_response(registration, event.is_free, payment_url)
        ticket_email_payload = None
        if registration_state == RegistrationState.CONFIRMED:
            ticket_email_payload = self._build_ticket_email_payload(event, registration)

        return RegistrationServiceResult(
            response=response,
            ticket_email_payload=ticket_email_payload,
        )

    def validate_state_transition(
        self,
        current_state: RegistrationState,
        next_state: RegistrationState,
    ) -> None:
        if next_state not in ALLOWED_REGISTRATION_STATE_TRANSITIONS[current_state]:
            raise RegistrationValidationError(
                f"Invalid registration state transition from '{current_state.value}' to '{next_state.value}'."
            )

    async def _validate_duplicate_email(self, event_id: str, payload: RegistrationCreateRequest) -> None:
        email_exists = await self.repository.email_exists_for_event(event_id, str(payload.email))
        if email_exists and not payload.acknowledge_duplicate:
            raise DuplicateRegistrationError()

    def _normalize_custom_field_values(self, custom_field_values: list) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for field_value in custom_field_values:
            if field_value.field_definition_id in normalized:
                raise RegistrationValidationError(
                    f"Duplicate submission for field_definition_id '{field_value.field_definition_id}'."
                )
            normalized[field_value.field_definition_id] = field_value.value.strip()
        return normalized

    def _validate_custom_field_values(self, event: Event, submitted_values: dict[str, str]) -> None:
        field_definitions = {field.id: field for field in event.field_definitions}

        invalid_field_ids = [field_id for field_id in submitted_values if field_id not in field_definitions]
        if invalid_field_ids:
            raise RegistrationValidationError(
                f"Unknown field_definition_id(s): {', '.join(sorted(invalid_field_ids))}."
            )

        missing_required = [
            field.label
            for field in event.field_definitions
            if field.is_required and field.id not in submitted_values
        ]
        if missing_required:
            raise RegistrationValidationError(
                f"Missing required custom fields: {', '.join(missing_required)}."
            )

        for field_definition in event.field_definitions:
            if field_definition.id not in submitted_values:
                continue
            value = submitted_values[field_definition.id]
            self._validate_custom_field_value(field_definition, value)

    def _validate_custom_field_value(self, field_definition: EventFieldDefinition, value: str) -> None:
        if field_definition.field_type == FieldType.TEXT:
            return
        if field_definition.field_type == FieldType.NUMBER:
            try:
                Decimal(value)
            except InvalidOperation as exc:
                raise RegistrationValidationError(
                    f"Field '{field_definition.label}' must be a valid numeric value."
                ) from exc
            return
        if field_definition.field_type == FieldType.DATE:
            try:
                date.fromisoformat(value)
            except ValueError as exc:
                raise RegistrationValidationError(
                    f"Field '{field_definition.label}' must be a valid ISO 8601 calendar date."
                ) from exc
            return
        if field_definition.field_type == FieldType.PHONE:
            if not PHONE_REGEX.fullmatch(value):
                raise RegistrationValidationError(
                    f"Field '{field_definition.label}' must be a valid phone number."
                )
            return
        if field_definition.field_type == FieldType.EMAIL:
            if not EMAIL_REGEX.fullmatch(value):
                raise RegistrationValidationError(
                    f"Field '{field_definition.label}' must be a valid email address."
                )
            return

    async def _determine_initial_state(self, event: Event) -> RegistrationState:
        if event.capacity is None:
            return RegistrationState.CONFIRMED if event.is_free else RegistrationState.PENDING_PAYMENT

        occupied_slots = await self.repository.count_capacity_occupying_registrations(event.id)
        if occupied_slots < event.capacity:
            return RegistrationState.CONFIRMED if event.is_free else RegistrationState.PENDING_PAYMENT

        if event.overflow_rule == OverflowRule.HARD_REJECTION:
            raise RegistrationConflictError("This event is fully booked and is not accepting further registrations.")

        return RegistrationState.WAITLISTED

    async def _generate_reg_id(self, event: Event) -> str:
        year = event.event_date.year
        for _ in range(REG_ID_RETRY_LIMIT):
            suffix = "".join(secrets.choice(REG_ID_SUFFIX_ALPHABET) for _ in range(REG_ID_SUFFIX_LENGTH))
            reg_id = f"{event.prefix}-{year}-{suffix}"
            if not await self.repository.reg_id_exists(reg_id):
                return reg_id
        raise RegistrationConflictError("Could not generate a unique registration ID. Please try again.")

    async def _next_waitlist_position(self, event_id: str) -> int:
        return await self.repository.count_waitlisted_registrations(event_id) + 1

    def _build_field_values(self, event: Event, submitted_values: dict[str, str]) -> list[RegistrationFieldValue]:
        field_order = {field.id: field for field in event.field_definitions}
        return [
            RegistrationFieldValue(
                field_definition_id=field_id,
                value=value,
            )
            for field_id, value in submitted_values.items()
            if field_id in field_order
        ]

    async def _create_pending_payment(self, registration: Registration, event: Event) -> str:
        gateway = self._resolve_gateway()
        reference = self._build_payment_reference(gateway, registration.reg_id)
        payment = Payment(
            gateway=gateway,
            payment_reference=reference,
            amount=event.price,
            status=PaymentStatus.PENDING,
            registration_id=registration.id,
        )
        await self.repository.create_payment(payment)
        return self._build_payment_url(gateway, reference)

    def _resolve_gateway(self) -> PaymentGateway:
        try:
            return PaymentGateway(self.settings.active_payment_gateway.lower())
        except ValueError as exc:
            raise RegistrationConflictError("The active payment gateway is not supported.") from exc

    def _build_payment_reference(self, gateway: PaymentGateway, reg_id: str) -> str:
        compact_reg_id = reg_id.replace("-", "")
        if gateway == PaymentGateway.MOCK:
            return f"MOCK_{compact_reg_id}"
        if gateway == PaymentGateway.PAYSTACK:
            return f"PAYSTACK_{compact_reg_id}"
        return f"SQUAD_{compact_reg_id}"

    def _build_payment_url(self, gateway: PaymentGateway, reference: str) -> str:
        if gateway == PaymentGateway.MOCK:
            return f"{self.settings.mock_payment_base_url.rstrip('/')}/mock-payment/pay?ref={reference}"
        if gateway == PaymentGateway.PAYSTACK:
            return f"{self.settings.paystack_checkout_base_url.rstrip('/')}/{reference.lower()}"
        return f"{self.settings.squad_checkout_base_url.rstrip('/')}/{reference.lower()}"

    def _build_response(
        self,
        registration: Registration,
        is_free_event: bool,
        payment_url: str | None,
    ) -> RegistrationCreateResponse:
        if registration.state == RegistrationState.CONFIRMED:
            message = f"Registration confirmed. A ticket has been sent to {registration.email}."
        elif registration.state == RegistrationState.PENDING_PAYMENT:
            message = "Registration created. Complete payment to confirm your spot."
        else:
            message = "The event is full. You have been added to the waitlist."

        return RegistrationCreateResponse(
            reg_id=registration.reg_id,
            state=registration.state,
            is_free=is_free_event,
            payment_url=payment_url,
            message=message,
        )

    def _build_ticket_email_payload(self, event: Event, registration: Registration) -> dict:
        return {
            "to": registration.email,
            "subject": f"Your ticket for {event.title}",
            "template": "ticket_confirmation",
            "context": {
                "reg_id": registration.reg_id,
                "event_title": event.title,
                "event_date": event.event_date.isoformat(),
                "location": event.location,
                "first_name": registration.first_name,
                "last_name": registration.last_name,
            },
        }
