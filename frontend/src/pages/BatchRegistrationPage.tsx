import { useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useFieldArray, useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";

import { getPublicEventDetail } from "../api/publicEvents";
import { createBatchRegistration } from "../api/publicRegistrations";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { EventFieldType, PublicEventCustomField, PublicEventDetail } from "../types/events";
import type { BatchRegistrationResponse } from "../types/registrations";

const MIN_PARTICIPANTS = 4;
const phoneRegex = /^(?:\+[1-9]\d{7,14}|234\d{10}|0\d{10})$/;
const emailRegex = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;

type BatchParticipantFormValues = {
  firstName: string;
  lastName: string;
  email: string;
  customValues: Record<string, string>;
};

type BatchRegistrationFormValues = {
  submitterName: string;
  submitterEmail: string;
  acknowledgeDuplicates: boolean;
  participants: BatchParticipantFormValues[];
};

export function BatchRegistrationPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const [duplicateWarningEmails, setDuplicateWarningEmails] = useState<string[]>([]);
  const [showAcknowledgeDuplicates, setShowAcknowledgeDuplicates] = useState(false);
  const [result, setResult] = useState<BatchRegistrationResponse | null>(null);

  if (!eventId) {
    return (
      <ErrorState
        title="Batch registration unavailable"
        message="The event identifier is missing from the current route."
      />
    );
  }

  const eventQuery = useQuery<PublicEventDetail, ApiError>({
    queryKey: queryKeys.publicEvents.detail(eventId),
    queryFn: ({ signal }) => getPublicEventDetail(eventId, signal),
  });

  const formSchema = useMemo(
    () => buildBatchRegistrationFormSchema(eventQuery.data?.custom_fields ?? []),
    [eventQuery.data?.custom_fields],
  );

  const form = useForm<BatchRegistrationFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      submitterName: "",
      submitterEmail: "",
      acknowledgeDuplicates: false,
      participants: Array.from({ length: MIN_PARTICIPANTS }, createBlankParticipant),
    },
  });

  const participantArray = useFieldArray({
    control: form.control,
    name: "participants",
  });

  const mutation = useMutation<BatchRegistrationResponse, ApiError, BatchRegistrationFormValues>({
    mutationFn: (values) =>
      createBatchRegistration(eventId, {
        submitter_name: values.submitterName.trim(),
        submitter_email: values.submitterEmail.trim(),
        acknowledge_duplicates: values.acknowledgeDuplicates,
        participants: values.participants.map((participant) => ({
          first_name: participant.firstName.trim(),
          last_name: participant.lastName.trim(),
          email: participant.email.trim(),
          custom_field_values: (eventQuery.data?.custom_fields ?? [])
            .map((field) => ({
              field_definition_id: field.id,
              value: (participant.customValues[field.id] ?? "").trim(),
            }))
            .filter((fieldValue) => fieldValue.value.length > 0),
        })),
      }),
    onSuccess: (response) => {
      setResult(response);
      setDuplicateWarningEmails([]);
      setShowAcknowledgeDuplicates(false);
      form.reset({
        submitterName: "",
        submitterEmail: "",
        acknowledgeDuplicates: false,
        participants: Array.from({ length: MIN_PARTICIPANTS }, createBlankParticipant),
      });
    },
    onError: (error) => {
      if (error.fieldErrors) {
        applyBatchApiFieldErrors(error.fieldErrors, form.setError, eventQuery.data?.custom_fields ?? []);
      }

      if (error.extras?.duplicate_emails?.length) {
        markDuplicateParticipantEmails(error.extras.duplicate_emails, form.getValues("participants"), form.setError);
      }

      if (error.extras?.duplicate_warning) {
        setShowAcknowledgeDuplicates(true);
        setDuplicateWarningEmails(error.extras.duplicate_emails ?? []);
        form.setError("acknowledgeDuplicates", {
          type: "server",
          message: "Confirm that you want to continue with the existing duplicate participant emails.",
        });
      }
    },
  });

  if (eventQuery.isPending) {
    return <LoadingState label="Loading batch registration form…" />;
  }

  if (eventQuery.isError) {
    return (
      <ErrorState
        title={eventQuery.error.code === "notFound" ? "Event not found" : "Could not load this batch form"}
        message={eventQuery.error.message}
      />
    );
  }

  const event = eventQuery.data;

  if (result) {
    return <BatchRegistrationResult event={event} result={result} />;
  }

  const rootError = form.formState.errors.root?.message ?? mutation.error?.message;
  const participantCount = participantArray.fields.length;
  const totalAmount = event.price * participantCount;

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Public"
          title={`Batch register for ${event.title}`}
          description="Provide one submitter record and at least four participants. Every participant receives the event’s configured custom fields."
        />

        <div className="event-detail-grid registration-layout">
          <article className="detail-card">
            <h2 className="detail-card__title">Event summary</h2>
            <dl className="detail-list">
              <div>
                <dt>Date</dt>
                <dd>{formatDateTime(event.event_date)}</dd>
              </div>
              <div>
                <dt>Location</dt>
                <dd>{event.location}</dd>
              </div>
              <div>
                <dt>Price per participant</dt>
                <dd>{event.is_free ? "Free" : formatPrice(event.price)}</dd>
              </div>
              <div>
                <dt>Current batch size</dt>
                <dd>{participantCount}</dd>
              </div>
              <div>
                <dt>Current total</dt>
                <dd>{event.is_free ? "Free" : formatPrice(totalAmount)}</dd>
              </div>
            </dl>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Before you submit</h2>
            <div className="summary-stack">
              <p className="detail-card__text">
                The backend requires a minimum of {MIN_PARTICIPANTS} participants for batch registration.
              </p>
              <p className="detail-card__text">
                For paid events, the backend returns one payment continuation URL for the whole batch.
              </p>
              <p className="detail-card__text">
                Required custom fields per participant:{" "}
                <strong>{event.custom_fields.filter((field) => field.is_required).length}</strong>
              </p>
            </div>
          </article>
        </div>
      </section>

      <section className="panel registration-form-card">
        <div className="section-header">
          <h2 className="section-title">Submitter and participant details</h2>
          <p className="section-note">
            The submitter is the point of contact for the batch. Each participant is registered individually within the batch.
          </p>
        </div>

        {rootError ? <div className="form-alert" role="alert">{rootError}</div> : null}

        {showAcknowledgeDuplicates && duplicateWarningEmails.length > 0 ? (
          <div className="form-alert" role="alert">
            These participant emails already exist for this event: {duplicateWarningEmails.join(", ")}.
          </div>
        ) : null}

        <form
          className="auth-form"
          onSubmit={form.handleSubmit((values) => {
            form.clearErrors("root");
            mutation.mutate(values);
          })}
          noValidate
        >
          <div className="custom-form-section">
            <div className="section-header">
              <h3 className="section-title">Submitter</h3>
              <p className="section-note">This person receives batch payment context and follow-up communication.</p>
            </div>

            <div className="form-grid">
              <div className="form-field">
                <label className="form-label" htmlFor="submitter-name">
                  Submitter name
                </label>
                <input
                  id="submitter-name"
                  type="text"
                  autoComplete="name"
                  className="form-input"
                  aria-invalid={form.formState.errors.submitterName ? "true" : "false"}
                  {...form.register("submitterName")}
                />
                {form.formState.errors.submitterName ? (
                  <p className="form-error">{form.formState.errors.submitterName.message}</p>
                ) : null}
              </div>

              <div className="form-field">
                <label className="form-label" htmlFor="submitter-email">
                  Submitter email
                </label>
                <input
                  id="submitter-email"
                  type="email"
                  autoComplete="email"
                  className="form-input"
                  aria-invalid={form.formState.errors.submitterEmail ? "true" : "false"}
                  {...form.register("submitterEmail")}
                />
                {form.formState.errors.submitterEmail ? (
                  <p className="form-error">{form.formState.errors.submitterEmail.message}</p>
                ) : null}
              </div>
            </div>
          </div>

          <div className="custom-form-section">
            <div className="section-header">
              <h3 className="section-title">Participants</h3>
              <div className="participant-toolbar">
                <p className="section-note">Minimum {MIN_PARTICIPANTS} participants required.</p>
                <button
                  type="button"
                  className="button-link"
                  onClick={() => participantArray.append(createBlankParticipant())}
                >
                  Add participant
                </button>
              </div>
            </div>

            <div className="participant-list">
              {participantArray.fields.map((participantField, index) => {
                const participantErrors = form.formState.errors.participants?.[index];

                return (
                  <article className="participant-card" key={participantField.id}>
                    <div className="participant-card__header">
                      <div>
                        <h4 className="participant-card__title">Participant {index + 1}</h4>
                        <p className="participant-card__subtitle">
                          Each participant receives their own registration ID.
                        </p>
                      </div>
                      <button
                        type="button"
                        className="button-link"
                        onClick={() => participantArray.remove(index)}
                        disabled={participantArray.fields.length <= MIN_PARTICIPANTS}
                        aria-disabled={participantArray.fields.length <= MIN_PARTICIPANTS}
                      >
                        Remove
                      </button>
                    </div>

                    <div className="form-grid">
                      <div className="form-field">
                        <label className="form-label" htmlFor={`participant-${index}-first-name`}>
                          First name
                        </label>
                        <input
                          id={`participant-${index}-first-name`}
                          type="text"
                          autoComplete="given-name"
                          className="form-input"
                          aria-invalid={participantErrors?.firstName ? "true" : "false"}
                          {...form.register(`participants.${index}.firstName`)}
                        />
                        {participantErrors?.firstName ? (
                          <p className="form-error">{participantErrors.firstName.message}</p>
                        ) : null}
                      </div>

                      <div className="form-field">
                        <label className="form-label" htmlFor={`participant-${index}-last-name`}>
                          Last name
                        </label>
                        <input
                          id={`participant-${index}-last-name`}
                          type="text"
                          autoComplete="family-name"
                          className="form-input"
                          aria-invalid={participantErrors?.lastName ? "true" : "false"}
                          {...form.register(`participants.${index}.lastName`)}
                        />
                        {participantErrors?.lastName ? (
                          <p className="form-error">{participantErrors.lastName.message}</p>
                        ) : null}
                      </div>
                    </div>

                    <div className="form-field">
                      <label className="form-label" htmlFor={`participant-${index}-email`}>
                        Email address
                      </label>
                      <input
                        id={`participant-${index}-email`}
                        type="email"
                        autoComplete="email"
                        className="form-input"
                        aria-invalid={participantErrors?.email ? "true" : "false"}
                        {...form.register(`participants.${index}.email`)}
                      />
                      {participantErrors?.email ? (
                        <p className="form-error">{participantErrors.email.message}</p>
                      ) : null}
                    </div>

                    {event.custom_fields.length > 0 ? (
                      <div className="custom-form-section">
                        <div className="section-header">
                          <h5 className="section-title">Participant custom fields</h5>
                          <p className="section-note">
                            These fields are repeated for every participant in the batch.
                          </p>
                        </div>

                        <div className="custom-form-fields">
                          {event.custom_fields.map((field) => {
                            const fieldPath = `participants.${index}.customValues.${field.id}` as const;
                            const fieldError = participantErrors?.customValues?.[field.id];
                            const inputId = `participant-${index}-custom-${field.id}`;
                            const errorId = `${inputId}-error`;

                            return (
                              <div className="form-field" key={field.id}>
                                <label className="form-label" htmlFor={inputId}>
                                  {field.label}
                                  {field.is_required ? " *" : ""}
                                </label>
                                <input
                                  id={inputId}
                                  type={resolveInputType(field.field_type)}
                                  inputMode={resolveInputMode(field.field_type)}
                                  className="form-input"
                                  aria-invalid={fieldError ? "true" : "false"}
                                  aria-describedby={fieldError ? errorId : undefined}
                                  {...form.register(fieldPath)}
                                />
                                <p className="field-hint">{buildFieldHint(field)}</p>
                                {fieldError ? (
                                  <p className="form-error" id={errorId}>
                                    {fieldError.message}
                                  </p>
                                ) : null}
                              </div>
                            );
                          })}
                        </div>
                      </div>
                    ) : null}
                  </article>
                );
              })}
            </div>
          </div>

          {showAcknowledgeDuplicates ? (
            <div className="checkbox-card">
              <label className="checkbox-field" htmlFor="acknowledge-duplicates">
                <input
                  id="acknowledge-duplicates"
                  type="checkbox"
                  className="checkbox-input"
                  {...form.register("acknowledgeDuplicates")}
                />
                <span>
                  I understand that one or more participant emails are already registered for this event and I want to continue with this batch submission.
                </span>
              </label>
              {form.formState.errors.acknowledgeDuplicates ? (
                <p className="form-error">{form.formState.errors.acknowledgeDuplicates.message}</p>
              ) : null}
            </div>
          ) : null}

          <div className="panel__actions">
            <button type="submit" className="button-link button-link--primary" disabled={mutation.isPending}>
              {mutation.isPending ? "Submitting…" : "Submit batch registration"}
            </button>
            <Link to={`/events/${event.id}`} className="button-link">
              Back to event details
            </Link>
          </div>
        </form>
      </section>
    </div>
  );
}

function BatchRegistrationResult({
  event,
  result,
}: {
  event: PublicEventDetail;
  result: BatchRegistrationResponse;
}) {
  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Batch registration submitted"
          title="Batch registration received"
          description={result.message}
        />

        <div className="event-detail-grid registration-layout">
          <article className="detail-card">
            <h2 className="detail-card__title">Batch summary</h2>
            <dl className="detail-list">
              <div>
                <dt>Batch ID</dt>
                <dd>{result.batch_id}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{formatRegistrationState(result.state)}</dd>
              </div>
              <div>
                <dt>Participants</dt>
                <dd>{result.participant_count}</dd>
              </div>
              <div>
                <dt>Total amount</dt>
                <dd>{result.total_amount === 0 ? "Free" : formatPrice(result.total_amount)}</dd>
              </div>
            </dl>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Next step</h2>
            <div className="summary-stack">
              <p className="detail-card__text">{buildNextStepMessage(result)}</p>
              <div className="panel__actions">
                {result.payment_url ? (
                  <a href={result.payment_url} className="button-link button-link--primary">
                    Continue to payment
                  </a>
                ) : null}
                <Link to={`/events/${event.id}`} className="button-link">
                  Back to event
                </Link>
                <Link to="/events" className="button-link">
                  Browse more events
                </Link>
              </div>
            </div>
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Participant registrations</h2>
          <p className="section-note">Each participant has their own registration ID inside this batch.</p>
        </div>

        <div className="participant-result-list">
          {result.participants.map((participant) => (
            <article className="participant-result-card" key={participant.reg_id}>
              <h3 className="participant-result-card__title">
                {participant.first_name} {participant.last_name}
              </h3>
              <dl className="detail-list">
                <div>
                  <dt>Email</dt>
                  <dd>{participant.email}</dd>
                </div>
                <div>
                  <dt>Registration ID</dt>
                  <dd>{participant.reg_id}</dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      </section>
    </div>
  );
}

function buildBatchRegistrationFormSchema(customFields: PublicEventCustomField[]) {
  return z
    .object({
      submitterName: z
        .string()
        .trim()
        .min(1, "Submitter name is required.")
        .max(255, "Submitter name must be 255 characters or fewer."),
      submitterEmail: z
        .string()
        .trim()
        .min(1, "Submitter email is required.")
        .regex(emailRegex, "Please enter a valid email address."),
      acknowledgeDuplicates: z.boolean().default(false),
      participants: z
        .array(
          z.object({
            firstName: z
              .string()
              .trim()
              .min(1, "First name is required.")
              .max(120, "First name must be 120 characters or fewer."),
            lastName: z
              .string()
              .trim()
              .min(1, "Last name is required.")
              .max(120, "Last name must be 120 characters or fewer."),
            email: z
              .string()
              .trim()
              .min(1, "Email address is required.")
              .regex(emailRegex, "Please enter a valid email address."),
            customValues: z.record(z.string()).default({}),
          }),
        )
        .min(MIN_PARTICIPANTS, `At least ${MIN_PARTICIPANTS} participants are required.`),
    })
    .superRefine((values, context) => {
      const seenEmails = new Map<string, number[]>();

      values.participants.forEach((participant, index) => {
        const normalizedEmail = participant.email.trim().toLowerCase();
        if (normalizedEmail) {
          const existingIndexes = seenEmails.get(normalizedEmail) ?? [];
          existingIndexes.push(index);
          seenEmails.set(normalizedEmail, existingIndexes);
        }

        for (const field of customFields) {
          const submittedValue = (participant.customValues[field.id] ?? "").trim();

          if (field.is_required && !submittedValue) {
            context.addIssue({
              code: z.ZodIssueCode.custom,
              message: `${field.label} is required.`,
              path: ["participants", index, "customValues", field.id],
            });
            continue;
          }

          if (!submittedValue) {
            continue;
          }

          const validationMessage = validateCustomFieldValue(field, submittedValue);
          if (validationMessage) {
            context.addIssue({
              code: z.ZodIssueCode.custom,
              message: validationMessage,
              path: ["participants", index, "customValues", field.id],
            });
          }
        }
      });

      for (const indexes of seenEmails.values()) {
        if (indexes.length < 2) {
          continue;
        }

        indexes.forEach((index) => {
          context.addIssue({
            code: z.ZodIssueCode.custom,
            message: "Each participant must have a unique email address within the batch.",
            path: ["participants", index, "email"],
          });
        });
      }
    });
}

function validateCustomFieldValue(field: PublicEventCustomField, value: string): string | null {
  switch (field.field_type) {
    case "text":
      return null;
    case "number":
      return Number.isNaN(Number(value)) ? `${field.label} must be a valid numeric value.` : null;
    case "date":
      return /^\d{4}-\d{2}-\d{2}$/.test(value) && !Number.isNaN(new Date(`${value}T00:00:00Z`).getTime())
        ? null
        : `${field.label} must be a valid calendar date.`;
    case "phone":
      return phoneRegex.test(value) ? null : `${field.label} must be a valid phone number.`;
    case "email":
      return emailRegex.test(value) ? null : `${field.label} must be a valid email address.`;
  }
}

function resolveInputType(fieldType: EventFieldType): React.HTMLInputTypeAttribute {
  switch (fieldType) {
    case "date":
      return "date";
    case "email":
      return "email";
    case "phone":
      return "tel";
    default:
      return "text";
  }
}

function resolveInputMode(fieldType: EventFieldType): React.HTMLAttributes<HTMLInputElement>["inputMode"] {
  switch (fieldType) {
    case "number":
      return "decimal";
    case "phone":
      return "tel";
    case "email":
      return "email";
    default:
      return "text";
  }
}

function buildFieldHint(field: PublicEventCustomField): string {
  switch (field.field_type) {
    case "date":
      return "Use the YYYY-MM-DD format.";
    case "number":
      return "Enter a numeric value only.";
    case "phone":
      return "Use a valid local or international phone number.";
    case "email":
      return "Enter a valid email address.";
    case "text":
      return field.is_required ? "This field is required." : "This field is optional.";
  }
}

function applyBatchApiFieldErrors(
  fieldErrors: Record<string, string[]>,
  setError: ReturnType<typeof useForm<BatchRegistrationFormValues>>["setError"],
  customFields: PublicEventCustomField[],
) {
  const fieldIdMap = new Set(customFields.map((field) => field.id));

  for (const [field, messages] of Object.entries(fieldErrors)) {
    const message = messages[0];
    if (!message) {
      continue;
    }

    if (field === "submitter_name") {
      setError("submitterName", { type: "server", message });
      continue;
    }

    if (field === "submitter_email") {
      setError("submitterEmail", { type: "server", message });
      continue;
    }

    const participantMatch = /^participants\.(\d+)\.(.+)$/.exec(field);
    if (participantMatch) {
      const index = Number(participantMatch[1]);
      const nestedField = participantMatch[2];

      if (nestedField === "first_name") {
        setError(`participants.${index}.firstName`, { type: "server", message });
        continue;
      }

      if (nestedField === "last_name") {
        setError(`participants.${index}.lastName`, { type: "server", message });
        continue;
      }

      if (nestedField === "email") {
        setError(`participants.${index}.email`, { type: "server", message });
        continue;
      }

      if (nestedField.startsWith("custom_field_values")) {
        setError("root", { type: "server", message });
        continue;
      }
    }

    if (fieldIdMap.has(field)) {
      setError("root", { type: "server", message });
      continue;
    }

    if (field === "participants") {
      setError("root", { type: "server", message });
      continue;
    }

    if (field === "form") {
      setError("root", { type: "server", message });
    }
  }
}

function markDuplicateParticipantEmails(
  duplicateEmails: string[],
  participants: BatchParticipantFormValues[],
  setError: ReturnType<typeof useForm<BatchRegistrationFormValues>>["setError"],
) {
  const loweredDuplicates = new Set(duplicateEmails.map((email) => email.toLowerCase()));

  participants.forEach((participant, index) => {
    if (loweredDuplicates.has(participant.email.trim().toLowerCase())) {
      setError(`participants.${index}.email`, {
        type: "server",
        message: "This participant email requires attention before you can proceed.",
      });
    }
  });
}

function createBlankParticipant(): BatchParticipantFormValues {
  return {
    firstName: "",
    lastName: "",
    email: "",
    customValues: {},
  };
}

function formatRegistrationState(state: BatchRegistrationResponse["state"]): string {
  switch (state) {
    case "confirmed":
      return "Confirmed";
    case "pending_payment":
      return "Pending payment";
    case "waitlisted":
      return "Waitlisted";
    case "failed":
      return "Failed";
    case "cancelled":
      return "Cancelled";
  }
}

function buildNextStepMessage(result: BatchRegistrationResponse): string {
  if (result.state === "pending_payment") {
    return "Use the payment link to complete payment and confirm every participant in the batch.";
  }

  if (result.state === "waitlisted") {
    return "No payment is required right now. Keep the batch and participant registration IDs for future lookup and updates.";
  }

  return "Keep the batch and participant registration IDs safe. They can be used for follow-up workflows once those pages are connected.";
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
}
