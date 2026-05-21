import { useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";

import { getPublicEventDetail } from "../api/publicEvents";
import { createSingleRegistration } from "../api/publicRegistrations";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type {
  EventFieldType,
  PublicEventCustomField,
  PublicEventDetail,
} from "../types/events";
import type { SingleRegistrationResponse } from "../types/registrations";

const phoneRegex = /^(?:\+[1-9]\d{7,14}|234\d{10}|0\d{10})$/;
const emailRegex = /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+$/;

type RegistrationFormValues = {
  firstName: string;
  lastName: string;
  email: string;
  acknowledgeDuplicate: boolean;
  customValues: Record<string, string>;
};

export function SingleRegistrationPage() {
  const { eventId } = useParams<{ eventId: string }>();
  const [duplicateConfirmationVisible, setDuplicateConfirmationVisible] = useState(false);
  const [result, setResult] = useState<SingleRegistrationResponse | null>(null);

  if (!eventId) {
    return (
      <ErrorState
        title="Registration unavailable"
        message="The event identifier is missing from the current route."
      />
    );
  }

  const eventQuery = useQuery<PublicEventDetail, ApiError>({
    queryKey: queryKeys.publicEvents.detail(eventId),
    queryFn: ({ signal }) => getPublicEventDetail(eventId, signal),
  });

  const formSchema = useMemo(
    () => buildRegistrationFormSchema(eventQuery.data?.custom_fields ?? []),
    [eventQuery.data?.custom_fields],
  );

  const form = useForm<RegistrationFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      firstName: "",
      lastName: "",
      email: "",
      acknowledgeDuplicate: false,
      customValues: {},
    },
  });

  const mutation = useMutation<SingleRegistrationResponse, ApiError, RegistrationFormValues>({
    mutationFn: (values) =>
      createSingleRegistration(eventId, {
        first_name: values.firstName.trim(),
        last_name: values.lastName.trim(),
        email: values.email.trim(),
        acknowledge_duplicate: values.acknowledgeDuplicate,
        custom_field_values: (eventQuery.data?.custom_fields ?? [])
          .map((field) => ({
            field_definition_id: field.id,
            value: (values.customValues[field.id] ?? "").trim(),
          }))
          .filter((fieldValue) => fieldValue.value.length > 0),
      }),
    onSuccess: (response) => {
      setResult(response);
      setDuplicateConfirmationVisible(false);
      form.reset({
        firstName: "",
        lastName: "",
        email: "",
        acknowledgeDuplicate: false,
        customValues: {},
      });
    },
    onError: (error) => {
      if (error.fieldErrors) {
        applyApiFieldErrors(error.fieldErrors, form.setError, eventQuery.data?.custom_fields ?? []);
      }

      if (error.extras?.duplicate_email) {
        setDuplicateConfirmationVisible(true);
        form.setValue("acknowledgeDuplicate", false);
        form.setError("acknowledgeDuplicate", {
          type: "server",
          message: "Confirm that you want to continue with a duplicate registration attempt.",
        });
      }
    },
  });

  if (eventQuery.isPending) {
    return <LoadingState label="Loading registration form…" />;
  }

  if (eventQuery.isError) {
    return (
      <ErrorState
        title={eventQuery.error.code === "notFound" ? "Event not found" : "Could not load this registration form"}
        message={eventQuery.error.message}
      />
    );
  }

  const event = eventQuery.data;

  if (result) {
    return <RegistrationResult event={event} result={result} />;
  }

  const rootError = form.formState.errors.root?.message ?? mutation.error?.message;

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Public"
          title={`Register for ${event.title}`}
          description="Submit the required attendee information exactly as requested by the event configuration."
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
                <dt>Price</dt>
                <dd>{event.is_free ? "Free" : formatPrice(event.price)}</dd>
              </div>
              <div>
                <dt>Capacity</dt>
                <dd>{event.capacity ?? "Unlimited"}</dd>
              </div>
            </dl>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Before you submit</h2>
            <div className="summary-stack">
              <p className="detail-card__text">
                The backend validates these details against the event’s live registration rules.
              </p>
              <p className="detail-card__text">
                If payment is required, you will receive a registration ID and a payment continuation link after the form is accepted.
              </p>
              <p className="detail-card__text">
                Required custom fields:{" "}
                <strong>
                  {event.custom_fields.filter((field) => field.is_required).length}
                </strong>
              </p>
            </div>
          </article>
        </div>
      </section>

      <section className="panel registration-form-card">
        <div className="section-header">
          <h2 className="section-title">Attendee details</h2>
          <p className="section-note">All fields marked required must be completed before you can submit.</p>
        </div>

        {rootError ? <div className="form-alert" role="alert">{rootError}</div> : null}

        <form
          className="auth-form"
          onSubmit={form.handleSubmit((values) => {
            form.clearErrors("root");

            if (duplicateConfirmationVisible && !values.acknowledgeDuplicate) {
              form.setError("acknowledgeDuplicate", {
                type: "manual",
                message: "Confirm that you want to continue before resubmitting.",
              });
              return;
            }

            mutation.mutate(values);
          })}
          noValidate
        >
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label" htmlFor="first-name">
                First name
              </label>
              <input
                id="first-name"
                type="text"
                autoComplete="given-name"
                className="form-input"
                aria-invalid={form.formState.errors.firstName ? "true" : "false"}
                {...form.register("firstName")}
              />
              {form.formState.errors.firstName ? (
                <p className="form-error" id="first-name-error">
                  {form.formState.errors.firstName.message}
                </p>
              ) : null}
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="last-name">
                Last name
              </label>
              <input
                id="last-name"
                type="text"
                autoComplete="family-name"
                className="form-input"
                aria-invalid={form.formState.errors.lastName ? "true" : "false"}
                {...form.register("lastName")}
              />
              {form.formState.errors.lastName ? (
                <p className="form-error" id="last-name-error">
                  {form.formState.errors.lastName.message}
                </p>
              ) : null}
            </div>
          </div>

          <div className="form-field">
            <label className="form-label" htmlFor="email">
              Email address
            </label>
            <input
              id="email"
              type="email"
              autoComplete="email"
              className="form-input"
              aria-invalid={form.formState.errors.email ? "true" : "false"}
              {...form.register("email")}
            />
            {form.formState.errors.email ? (
              <p className="form-error" id="email-error">
                {form.formState.errors.email.message}
              </p>
            ) : null}
          </div>

          {event.custom_fields.length > 0 ? (
            <div className="custom-form-section">
              <div className="section-header">
                <h3 className="section-title">Custom event fields</h3>
                <p className="section-note">
                  These inputs are configured per event and are submitted exactly as entered.
                </p>
              </div>

              <div className="custom-form-fields">
                {event.custom_fields.map((field) => {
                  const fieldName = `customValues.${field.id}` as const;
                  const fieldError = form.formState.errors.customValues?.[field.id];
                  const inputId = `custom-field-${field.id}`;
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
                        {...form.register(fieldName)}
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

          {duplicateConfirmationVisible ? (
            <div className="checkbox-card">
              <label className="checkbox-field" htmlFor="acknowledge-duplicate">
                <input
                  id="acknowledge-duplicate"
                  type="checkbox"
                  className="checkbox-input"
                  {...form.register("acknowledgeDuplicate")}
                />
                <span>
                  I understand that this email has already been used for this event and I want to continue with this submission.
                </span>
              </label>
              {form.formState.errors.acknowledgeDuplicate ? (
                <p className="form-error">
                  {form.formState.errors.acknowledgeDuplicate.message}
                </p>
              ) : null}
            </div>
          ) : null}

          <div className="panel__actions">
            <button
              type="submit"
              className="button-link button-link--primary"
              disabled={mutation.isPending}
            >
              {mutation.isPending ? "Submitting…" : "Submit registration"}
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

function RegistrationResult({
  event,
  result,
}: {
  event: PublicEventDetail;
  result: SingleRegistrationResponse;
}) {
  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Registration submitted"
          title="Registration received"
          description={result.message}
        />

        <div className="event-detail-grid registration-layout">
          <article className="detail-card">
            <h2 className="detail-card__title">Registration summary</h2>
            <dl className="detail-list">
              <div>
                <dt>Registration ID</dt>
                <dd>{result.reg_id}</dd>
              </div>
              <div>
                <dt>Status</dt>
                <dd>{formatRegistrationState(result.state)}</dd>
              </div>
              <div>
                <dt>Event</dt>
                <dd>{event.title}</dd>
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
    </div>
  );
}

function buildRegistrationFormSchema(customFields: PublicEventCustomField[]) {
  return z
    .object({
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
      acknowledgeDuplicate: z.boolean().default(false),
      customValues: z.record(z.string()).default({}),
    })
    .superRefine((values, context) => {
      for (const field of customFields) {
        const submittedValue = (values.customValues[field.id] ?? "").trim();

        if (field.is_required && !submittedValue) {
          context.addIssue({
            code: z.ZodIssueCode.custom,
            message: `${field.label} is required.`,
            path: ["customValues", field.id],
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
            path: ["customValues", field.id],
          });
        }
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

function applyApiFieldErrors(
  fieldErrors: Record<string, string[]>,
  setError: ReturnType<typeof useForm<RegistrationFormValues>>["setError"],
  customFields: PublicEventCustomField[],
) {
  const fieldIdMap = new Set(customFields.map((field) => field.id));

  for (const [field, messages] of Object.entries(fieldErrors)) {
    const message = messages[0];
    if (!message) {
      continue;
    }

    if (field === "first_name") {
      setError("firstName", { type: "server", message });
      continue;
    }

    if (field === "last_name") {
      setError("lastName", { type: "server", message });
      continue;
    }

    if (field === "email") {
      setError("email", { type: "server", message });
      continue;
    }

    if (field.startsWith("custom_field_values")) {
      setError("root", { type: "server", message });
      continue;
    }

    if (fieldIdMap.has(field)) {
      setError(`customValues.${field}` as const, { type: "server", message });
      continue;
    }

    if (field === "form") {
      setError("root", { type: "server", message });
    }
  }
}

function formatRegistrationState(state: SingleRegistrationResponse["state"]): string {
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

function buildNextStepMessage(result: SingleRegistrationResponse): string {
  if (result.state === "pending_payment") {
    return "Use the payment link to complete payment and confirm the registration.";
  }

  if (result.state === "waitlisted") {
    return "No payment is required right now. Keep the registration ID for future lookup and notifications.";
  }

  return "Keep the registration ID safe. You can use it later in the lookup flow once that page is connected.";
}

function formatPrice(value: number): string {
  return new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "NGN",
    maximumFractionDigits: 0,
  }).format(value);
}
