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
    DuplicateBatchExistingRegistrationError,
    DuplicateBatchSubmissionError,
    DuplicateRegistrationError,
    EventConflictError,
    EventNotFoundError,
    RegistrationConflictError,
    RegistrationValidationError,
)
from app.models.event import Event, EventFieldDefinition, EventState, FieldType, OverflowRule
from app.models.registration import BatchRegistration, Registration, RegistrationFieldValue, RegistrationState
from app.repositories.registration_repository import RegistrationRepository
from app.services.email_templates import build_ticket_email_message
from app.services.payment_service import PaymentService
from app.schemas.registration import (
    BatchParticipantRegistrationInput,
    BatchRegistrationCreateRequest,
    BatchRegistrationCreateResponse,
    BatchRegistrationParticipantResponse,
    BatchRegistrationServiceResult,
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
    RegistrationState.CONFIRMED: {RegistrationState.CANCELLED},
    RegistrationState.WAITLISTED: {
        RegistrationState.PENDING_PAYMENT,
        RegistrationState.CONFIRMED,
        RegistrationState.CANCELLED,
    },
    RegistrationState.FAILED: set(),
    RegistrationState.CANCELLED: set(),
}


@dataclass
class RegistrationService:
    session: AsyncSession
    settings: Settings

    def __post_init__(self) -> None:
        self.repository = RegistrationRepository(self.session)
        self.payment_service = PaymentService(self.session, self.settings)

    async def create_single_registration(
        self,
        event_id: str,
        payload: RegistrationCreateRequest,
    ) -> RegistrationServiceResult:
        event = await self._load_public_event_or_raise(event_id)
        event = await self._lock_capacity_managed_event(event)

        await self._validate_duplicate_email(event.id, payload.email, payload.acknowledge_duplicate)

        submitted_values = self._normalize_custom_field_values(payload.custom_field_values)
        self._validate_custom_field_values(event, submitted_values)

        registration_state = await self._determine_initial_state(event)
        reg_id = await self._generate_reg_id(event)
        registration = Registration(
            event_id=event.id,
            first_name=payload.first_name,
            last_name=payload.last_name,
            email=payload.email,
            reg_id=reg_id,
            state=registration_state,
            waitlist_position=(
                await self._next_waitlist_position(event.id)
                if registration_state == RegistrationState.WAITLISTED
                else None
            ),
        )
        registration.field_values = self._build_field_values(submitted_values)

        payment_url: str | None = None
        try:
            await self.repository.create_registration(registration)
            if registration_state == RegistrationState.PENDING_PAYMENT:
                payment_result = await self.payment_service.initialize_registration_payment(
                    registration=registration,
                    event=event,
                )
                payment_url = payment_result.checkout_url
            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise EventConflictError("The registration could not be saved because it conflicts with existing data.") from exc

        response = self._build_single_response(registration, event.is_free, payment_url)
        ticket_email_message = (
            build_ticket_email_message(self.settings, event=event, registration=registration)
            if registration_state == RegistrationState.CONFIRMED
            else None
        )
        return RegistrationServiceResult(response=response, ticket_email_message=ticket_email_message)

    async def create_batch_registration(
        self,
        event_id: str,
        payload: BatchRegistrationCreateRequest,
    ) -> BatchRegistrationServiceResult:
        event = await self._load_public_event_or_raise(event_id)
        event = await self._lock_capacity_managed_event(event)

        if len(payload.participants) < 4:
            raise RegistrationValidationError("Batch registration requires a minimum of 4 participants.")

        participant_emails = [participant.email for participant in payload.participants]
        self._validate_intra_batch_duplicate_emails(participant_emails)
        await self._validate_existing_batch_duplicate_emails(
            event.id,
            participant_emails,
            payload.acknowledge_duplicates,
        )

        batch_state = await self._determine_batch_initial_state(event, len(payload.participants))
        total_amount = event.price * len(payload.participants)
        batch_registration = BatchRegistration(
            event_id=event.id,
            submitter_name=payload.submitter_name,
            submitter_email=payload.submitter_email,
            total_amount=total_amount,
            payment_reference=None,
        )

        participant_responses: list[BatchRegistrationParticipantResponse] = []
        ticket_email_messages = []
        payment_url: str | None = None

        try:
            await self.repository.create_batch_registration(batch_registration)
            starting_waitlist_position = (
                await self._next_waitlist_position(event.id)
                if batch_state == RegistrationState.WAITLISTED
                else None
            )

            for index, participant in enumerate(payload.participants):
                submitted_values = self._normalize_custom_field_values(participant.custom_field_values)
                self._validate_custom_field_values(event, submitted_values)

                reg_id = await self._generate_reg_id(event)
                registration = Registration(
                    event_id=event.id,
                    first_name=participant.first_name,
                    last_name=participant.last_name,
                    email=participant.email,
                    reg_id=reg_id,
                    state=batch_state,
                    batch_id=batch_registration.id,
                    waitlist_position=(
                        starting_waitlist_position + index
                        if starting_waitlist_position is not None
                        else None
                    ),
                )
                registration.field_values = self._build_field_values(submitted_values)
                await self.repository.create_registration(registration)

                participant_responses.append(
                    BatchRegistrationParticipantResponse(
                        reg_id=registration.reg_id,
                        first_name=registration.first_name,
                        last_name=registration.last_name,
                        email=registration.email,
                    )
                )
                if batch_state == RegistrationState.CONFIRMED:
                    ticket_email_messages.append(
                        build_ticket_email_message(self.settings, event=event, registration=registration)
                    )

            if batch_state == RegistrationState.PENDING_PAYMENT:
                payment_result = await self.payment_service.initialize_batch_payment(
                    batch_registration=batch_registration
                )
                payment_url = payment_result.checkout_url

            await self.session.flush()
        except IntegrityError as exc:
            await self.session.rollback()
            raise EventConflictError("The registration could not be saved because it conflicts with existing data.") from exc

        response = self._build_batch_response(
            batch_registration=batch_registration,
            participant_count=len(payload.participants),
            participants=participant_responses,
            state=batch_state,
            payment_url=payment_url,
        )
        return BatchRegistrationServiceResult(response=response, ticket_email_messages=ticket_email_messages)

    def validate_state_transition(
        self,
        current_state: RegistrationState,
        next_state: RegistrationState,
    ) -> None:
        if next_state not in ALLOWED_REGISTRATION_STATE_TRANSITIONS[current_state]:
            raise RegistrationValidationError(
                f"Invalid registration state transition from '{current_state.value}' to '{next_state.value}'."
            )

    async def _load_public_event_or_raise(self, event_id: str) -> Event:
        event = await self.repository.get_event_with_fields(event_id)
        self._ensure_event_accepts_registration(event)
        return event

    async def _lock_capacity_managed_event(self, event: Event) -> Event:
        if event.capacity is None:
            return event
        locked_event = await self.repository.lock_event(event.id)
        self._ensure_event_accepts_registration(locked_event)
        return locked_event

    def _ensure_event_accepts_registration(self, event: Event | None) -> None:
        if event is None or event.state == EventState.DRAFT:
            raise EventNotFoundError("Event not found.")
        if event.state in {EventState.CANCELLED, EventState.COMPLETED}:
            raise RegistrationConflictError("This event is no longer accepting registrations.")

    async def _validate_duplicate_email(self, event_id: str, email: str, acknowledged: bool) -> None:
        email_exists = await self.repository.email_exists_for_event(event_id, email)
        if email_exists and not acknowledged:
            raise DuplicateRegistrationError()

    def _validate_intra_batch_duplicate_emails(self, participant_emails: list[str]) -> None:
        seen: set[str] = set()
        duplicates: set[str] = set()
        for email in participant_emails:
            lowered = email.lower()
            if lowered in seen:
                duplicates.add(lowered)
            seen.add(lowered)
        if duplicates:
            raise DuplicateBatchSubmissionError(sorted(duplicates))

    async def _validate_existing_batch_duplicate_emails(
        self,
        event_id: str,
        participant_emails: list[str],
        acknowledged: bool,
    ) -> None:
        duplicate_emails = await self.repository.existing_emails_for_event(event_id, participant_emails)
        if duplicate_emails and not acknowledged:
            raise DuplicateBatchExistingRegistrationError(duplicate_emails)

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
            self._validate_custom_field_value(field_definition, submitted_values[field_definition.id])

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
        if field_definition.field_type == FieldType.EMAIL and not EMAIL_REGEX.fullmatch(value):
            raise RegistrationValidationError(
                f"Field '{field_definition.label}' must be a valid email address."
            )

    async def _determine_initial_state(self, event: Event) -> RegistrationState:
        if event.capacity is None:
            return RegistrationState.CONFIRMED if event.is_free else RegistrationState.PENDING_PAYMENT

        occupied_slots = await self.repository.count_capacity_occupying_registrations(event.id)
        if occupied_slots < event.capacity:
            return RegistrationState.CONFIRMED if event.is_free else RegistrationState.PENDING_PAYMENT

        if event.overflow_rule == OverflowRule.HARD_REJECTION:
            raise RegistrationConflictError("This event is fully booked and is not accepting further registrations.")

        return RegistrationState.WAITLISTED

    async def _determine_batch_initial_state(self, event: Event, participant_count: int) -> RegistrationState:
        if event.capacity is None:
            return RegistrationState.CONFIRMED if event.is_free else RegistrationState.PENDING_PAYMENT

        occupied_slots = await self.repository.count_capacity_occupying_registrations(event.id)
        available_slots = max(event.capacity - occupied_slots, 0)
        if available_slots >= participant_count:
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

    def _build_field_values(self, submitted_values: dict[str, str]) -> list[RegistrationFieldValue]:
        return [
            RegistrationFieldValue(
                field_definition_id=field_id,
                value=value,
            )
            for field_id, value in submitted_values.items()
        ]

    def _build_single_response(
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

    def _build_batch_response(
        self,
        *,
        batch_registration: BatchRegistration,
        participant_count: int,
        participants: list[BatchRegistrationParticipantResponse],
        state: RegistrationState,
        payment_url: str | None,
    ) -> BatchRegistrationCreateResponse:
        if state == RegistrationState.CONFIRMED:
            message = "Batch registration confirmed. Tickets have been sent to all participants."
        elif state == RegistrationState.PENDING_PAYMENT:
            message = "Batch registration created. Complete payment to confirm all spots."
        else:
            message = "The event is full. This batch has been added to the waitlist."

        return BatchRegistrationCreateResponse(
            batch_id=batch_registration.id,
            total_amount=batch_registration.total_amount,
            currency="NGN",
            participant_count=participant_count,
            state=state,
            payment_url=payment_url,
            participants=participants,
            message=message,
        )
