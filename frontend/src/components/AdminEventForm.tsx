import { useEffect, useMemo } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useFieldArray, useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { z } from "zod";

import { ApiError } from "../lib/apiError";
import { fromDateTimeLocalInputValue, toDateTimeLocalInputValue } from "../lib/date";
import type {
  AdminEventCreateRequest,
  AdminEventDetail,
  AdminEventUpdateRequest,
  NotificationMethod,
  OverflowRule,
  PriceChangeScope,
} from "../types/adminEvents";
import { notificationMethodSchema, overflowRuleSchema, priceChangeScopeSchema } from "../types/adminEvents";
import { eventFieldTypeSchema, type EventFieldType } from "../types/events";

type AdminEventFormMode = "create" | "edit";

type AdminEventFormValues = {
  title: string;
  description: string;
  eventDate: string;
  location: string;
  prefix: string;
  price: string;
  capacity: string;
  overflowRule: OverflowRule;
  customFields: Array<{
    label: string;
    fieldType: EventFieldType;
    isRequired: boolean;
    displayOrder: string;
  }>;
  priceChangeScope: "" | PriceChangeScope;
  notificationMethod: "" | NotificationMethod;
  notificationBody: string;
};

type CustomFieldPath =
  | `customFields.${number}.label`
  | `customFields.${number}.fieldType`
  | `customFields.${number}.isRequired`
  | `customFields.${number}.displayOrder`;

type AdminEventFormProps = {
  backHref: string;
  event?: AdminEventDetail;
  isSubmitting: boolean;
  mode: AdminEventFormMode;
  onSubmit: (payload: AdminEventCreateRequest | AdminEventUpdateRequest) => Promise<void>;
  submitLabel: string;
};

export function AdminEventForm({
  backHref,
  event,
  isSubmitting,
  mode,
  onSubmit,
  submitLabel,
}: AdminEventFormProps) {
  const initialPrice = event?.price ?? 0;
  const formSchema = useMemo(
    () => buildAdminEventFormSchema({ initialPrice, mode }),
    [initialPrice, mode],
  );
  const defaultValues = useMemo(() => buildDefaultValues(mode, event), [event, mode]);

  const form = useForm<AdminEventFormValues>({
    resolver: zodResolver(formSchema),
    defaultValues,
  });

  useEffect(() => {
    form.reset(defaultValues);
  }, [defaultValues, form]);

  const fieldArray = useFieldArray({
    control: form.control,
    name: "customFields",
  });

  const priceValue = form.watch("price");
  const priceChangeScopeValue = form.watch("priceChangeScope");
  const parsedPrice = parseWholeNumber(priceValue);
  const priceChanged = mode === "edit" && parsedPrice !== null && parsedPrice !== initialPrice;

  useEffect(() => {
    if (mode === "edit" && !priceChanged) {
      form.setValue("priceChangeScope", "");
      form.setValue("notificationMethod", "");
      form.setValue("notificationBody", "");
    }
  }, [form, mode, priceChanged]);

  useEffect(() => {
    if (priceChangeScopeValue !== "all_existing_confirmed") {
      form.setValue("notificationMethod", "");
      form.setValue("notificationBody", "");
    }
  }, [form, priceChangeScopeValue]);

  const rootError = form.formState.errors.root?.message;

  return (
    <form
      className="auth-form"
      noValidate
      onSubmit={form.handleSubmit(async (values) => {
        form.clearErrors("root");

        try {
          if (mode === "create") {
            await onSubmit(buildCreatePayload(values));
            return;
          }

          await onSubmit(buildUpdatePayload(values, initialPrice));
        } catch (error) {
          applyAdminEventFormApiErrors(error, form.setError);
        }
      })}
    >
      {rootError ? (
        <div className="form-alert" role="alert">
          {rootError}
        </div>
      ) : null}

      <div className="form-grid">
        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-title">
            Title
          </label>
          <input
            id="admin-event-title"
            type="text"
            className="form-input"
            aria-invalid={form.formState.errors.title ? "true" : "false"}
            {...form.register("title")}
          />
          {form.formState.errors.title ? (
            <p className="form-error">{form.formState.errors.title.message}</p>
          ) : null}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-prefix">
            Prefix
          </label>
          <input
            id="admin-event-prefix"
            type="text"
            autoComplete="off"
            className="form-input"
            aria-invalid={form.formState.errors.prefix ? "true" : "false"}
            disabled={mode === "edit"}
            {...form.register("prefix")}
          />
          <p className="field-hint">
            {mode === "create"
              ? "Use 2 to 5 uppercase letters or numbers."
              : "Event prefixes cannot be changed after creation."}
          </p>
          {form.formState.errors.prefix ? (
            <p className="form-error">{form.formState.errors.prefix.message}</p>
          ) : null}
        </div>
      </div>

      <div className="form-field">
        <label className="form-label" htmlFor="admin-event-description">
          Description
        </label>
        <textarea
          id="admin-event-description"
          rows={5}
          className="form-input form-textarea"
          aria-invalid={form.formState.errors.description ? "true" : "false"}
          {...form.register("description")}
        />
        {form.formState.errors.description ? (
          <p className="form-error">{form.formState.errors.description.message}</p>
        ) : null}
      </div>

      <div className="form-grid">
        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-date">
            Event date and time
          </label>
          <input
            id="admin-event-date"
            type="datetime-local"
            className="form-input"
            aria-invalid={form.formState.errors.eventDate ? "true" : "false"}
            {...form.register("eventDate")}
          />
          {form.formState.errors.eventDate ? (
            <p className="form-error">{form.formState.errors.eventDate.message}</p>
          ) : null}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-location">
            Location
          </label>
          <input
            id="admin-event-location"
            type="text"
            className="form-input"
            aria-invalid={form.formState.errors.location ? "true" : "false"}
            {...form.register("location")}
          />
          {form.formState.errors.location ? (
            <p className="form-error">{form.formState.errors.location.message}</p>
          ) : null}
        </div>
      </div>

      <div className="form-grid">
        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-price">
            Price (NGN)
          </label>
          <input
            id="admin-event-price"
            type="number"
            min="0"
            step="1"
            className="form-input"
            aria-invalid={form.formState.errors.price ? "true" : "false"}
            {...form.register("price")}
          />
          <p className="field-hint">
            Enter 0 to make the event free.
          </p>
          {form.formState.errors.price ? (
            <p className="form-error">{form.formState.errors.price.message}</p>
          ) : null}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-capacity">
            Capacity
          </label>
          <input
            id="admin-event-capacity"
            type="number"
            min="1"
            step="1"
            className="form-input"
            aria-invalid={form.formState.errors.capacity ? "true" : "false"}
            {...form.register("capacity")}
          />
          <p className="field-hint">
            Leave blank for unlimited capacity.
          </p>
          {form.formState.errors.capacity ? (
            <p className="form-error">{form.formState.errors.capacity.message}</p>
          ) : null}
        </div>
      </div>

      {mode === "create" ? (
        <div className="form-field">
          <label className="form-label" htmlFor="admin-event-overflow-rule">
            Overflow rule
          </label>
          <select
            id="admin-event-overflow-rule"
            className="form-input"
            aria-invalid={form.formState.errors.overflowRule ? "true" : "false"}
            {...form.register("overflowRule")}
          >
            <option value="hard_rejection">Hard rejection</option>
            <option value="waitlist">Waitlist</option>
          </select>
          <p className="field-hint">
            Waitlist behavior is enforced by the backend based on the event pricing and capacity rules.
          </p>
          {form.formState.errors.overflowRule ? (
            <p className="form-error">{form.formState.errors.overflowRule.message}</p>
          ) : null}
        </div>
      ) : null}

      {mode === "edit" && priceChanged ? (
        <section className="detail-card">
          <div className="section-header">
            <h3 className="section-title">Price change scope</h3>
            <p className="section-note">
              Only use notification settings when applying the new price to existing confirmed registrations.
            </p>
          </div>

          <div className="auth-form">
            <div className="form-field">
              <label className="form-label" htmlFor="admin-event-price-scope">
                Price change scope
              </label>
              <select
                id="admin-event-price-scope"
                className="form-input"
                aria-invalid={form.formState.errors.priceChangeScope ? "true" : "false"}
                {...form.register("priceChangeScope")}
              >
                <option value="">Select how the price change should apply</option>
                <option value="new_registrations_only">New registrations only</option>
                <option value="all_existing_confirmed">All existing confirmed registrations</option>
              </select>
              {form.formState.errors.priceChangeScope ? (
                <p className="form-error">{form.formState.errors.priceChangeScope.message}</p>
              ) : null}
            </div>

            {priceChangeScopeValue === "all_existing_confirmed" ? (
              <>
                <div className="form-field">
                  <label className="form-label" htmlFor="admin-event-price-notification-method">
                    Notification method
                  </label>
                  <select
                    id="admin-event-price-notification-method"
                    className="form-input"
                    aria-invalid={form.formState.errors.notificationMethod ? "true" : "false"}
                    {...form.register("notificationMethod")}
                  >
                    <option value="">Select a notification method</option>
                    <option value="in_app">In-app notification</option>
                    <option value="email">Email</option>
                  </select>
                  {form.formState.errors.notificationMethod ? (
                    <p className="form-error">{form.formState.errors.notificationMethod.message}</p>
                  ) : null}
                </div>

                <div className="form-field">
                  <label className="form-label" htmlFor="admin-event-price-notification-body">
                    Notification body
                  </label>
                  <textarea
                    id="admin-event-price-notification-body"
                    rows={4}
                    className="form-input form-textarea"
                    aria-invalid={form.formState.errors.notificationBody ? "true" : "false"}
                    {...form.register("notificationBody")}
                  />
                  {form.formState.errors.notificationBody ? (
                    <p className="form-error">{form.formState.errors.notificationBody.message}</p>
                  ) : null}
                </div>
              </>
            ) : null}
          </div>
        </section>
      ) : null}

      <section className="detail-card">
        <div className="section-header">
          <h3 className="section-title">Custom registration fields</h3>
          <div className="panel__actions">
            <button
              type="button"
              className="button-link"
              onClick={() =>
                fieldArray.append({
                  label: "",
                  fieldType: "text",
                  isRequired: false,
                  displayOrder: String(getNextDisplayOrder(form.getValues("customFields"))),
                })
              }
            >
              Add custom field
            </button>
          </div>
        </div>

        {fieldArray.fields.length === 0 ? (
          <p className="detail-card__text">
            No custom fields are configured yet. Add only the extra attendee inputs this event actually needs.
          </p>
        ) : (
          <div className="field-array-list">
            {fieldArray.fields.map((field, index) => {
              const labelError = form.formState.errors.customFields?.[index]?.label;
              const fieldTypeError = form.formState.errors.customFields?.[index]?.fieldType;
              const displayOrderError = form.formState.errors.customFields?.[index]?.displayOrder;

              return (
                <article className="field-array-item" key={field.id}>
                  <div className="field-array-item__header">
                    <h4 className="field-array-item__title">Custom field {index + 1}</h4>
                    <button
                      type="button"
                      className="button-link"
                      onClick={() => fieldArray.remove(index)}
                    >
                      Remove
                    </button>
                  </div>

                  <div className="field-array-grid">
                    <div className="form-field">
                      <label className="form-label" htmlFor={`custom-field-label-${index}`}>
                        Label
                      </label>
                      <input
                        id={`custom-field-label-${index}`}
                        type="text"
                        className="form-input"
                        aria-invalid={labelError ? "true" : "false"}
                        {...form.register(`customFields.${index}.label` as const)}
                      />
                      {labelError ? <p className="form-error">{labelError.message}</p> : null}
                    </div>

                    <div className="form-field">
                      <label className="form-label" htmlFor={`custom-field-type-${index}`}>
                        Field type
                      </label>
                      <select
                        id={`custom-field-type-${index}`}
                        className="form-input"
                        aria-invalid={fieldTypeError ? "true" : "false"}
                        {...form.register(`customFields.${index}.fieldType` as const)}
                      >
                        <option value="text">Text</option>
                        <option value="number">Number</option>
                        <option value="date">Date</option>
                        <option value="phone">Phone</option>
                        <option value="email">Email</option>
                      </select>
                      {fieldTypeError ? <p className="form-error">{fieldTypeError.message}</p> : null}
                    </div>

                    <div className="form-field">
                      <label className="form-label" htmlFor={`custom-field-order-${index}`}>
                        Display order
                      </label>
                      <input
                        id={`custom-field-order-${index}`}
                        type="number"
                        min="1"
                        step="1"
                        className="form-input"
                        aria-invalid={displayOrderError ? "true" : "false"}
                        {...form.register(`customFields.${index}.displayOrder` as const)}
                      />
                      {displayOrderError ? (
                        <p className="form-error">{displayOrderError.message}</p>
                      ) : null}
                    </div>

                    <div className="form-field field-array-item__toggle">
                      <label className="checkbox-field" htmlFor={`custom-field-required-${index}`}>
                        <input
                          id={`custom-field-required-${index}`}
                          type="checkbox"
                          className="checkbox-input"
                          {...form.register(`customFields.${index}.isRequired` as const)}
                        />
                        <span>Required field</span>
                      </label>
                    </div>
                  </div>
                </article>
              );
            })}
          </div>
        )}
      </section>

      <div className="panel__actions">
        <button
          type="submit"
          className="button-link button-link--primary"
          disabled={isSubmitting}
        >
          {isSubmitting ? "Saving..." : submitLabel}
        </button>
        <Link to={backHref} className="button-link">
          Cancel
        </Link>
      </div>
    </form>
  );
}

function buildAdminEventFormSchema({
  initialPrice,
  mode,
}: {
  initialPrice: number;
  mode: AdminEventFormMode;
}) {
  return z
    .object({
      title: z.string().trim().min(1, "Title is required.").max(255, "Title must be 255 characters or fewer."),
      description: z.string().trim().min(1, "Description is required."),
      eventDate: z.string().trim().min(1, "Event date and time is required."),
      location: z.string().trim().min(1, "Location is required.").max(255, "Location must be 255 characters or fewer."),
      prefix: z
        .string()
        .trim()
        .regex(/^[A-Z0-9]{2,5}$/, "Prefix must be 2 to 5 uppercase letters or numbers."),
      price: z.string().trim().min(1, "Price is required."),
      capacity: z.string().trim().default(""),
      overflowRule: overflowRuleSchema,
      customFields: z.array(
        z.object({
          label: z.string().trim().min(1, "Field label is required.").max(255, "Field label must be 255 characters or fewer."),
          fieldType: eventFieldTypeSchema,
          isRequired: z.boolean().default(false),
          displayOrder: z.string().trim().min(1, "Display order is required."),
        }),
      ),
      priceChangeScope: z.union([z.literal(""), priceChangeScopeSchema]).default(""),
      notificationMethod: z.union([z.literal(""), notificationMethodSchema]).default(""),
      notificationBody: z.string().default(""),
    })
    .superRefine((values, context) => {
      if (!fromDateTimeLocalInputValue(values.eventDate)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["eventDate"],
          message: "Enter a valid date and time.",
        });
      }

      if (parseWholeNumber(values.price) === null) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["price"],
          message: "Price must be a whole number equal to or greater than zero.",
        });
      }

      if (values.capacity && parsePositiveWholeNumber(values.capacity) === null) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["capacity"],
          message: "Capacity must be a whole number greater than zero, or left blank.",
        });
      }

      const displayOrders = values.customFields
        .map((field, index) => ({ index, value: parsePositiveWholeNumber(field.displayOrder) }))
        .filter((field) => field.value !== null) as Array<{ index: number; value: number }>;

      for (const field of values.customFields) {
        if (parsePositiveWholeNumber(field.displayOrder) === null) {
          context.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["customFields", values.customFields.indexOf(field), "displayOrder"],
            message: "Display order must be a whole number greater than zero.",
          });
        }
      }

      const duplicates = new Set<number>();
      const seenDisplayOrders = new Set<number>();
      for (const entry of displayOrders) {
        if (seenDisplayOrders.has(entry.value)) {
          duplicates.add(entry.value);
        }
        seenDisplayOrders.add(entry.value);
      }

      if (duplicates.size > 0) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["customFields"],
          message: "Custom field display order values must be unique.",
        });
      }

      if (mode !== "edit") {
        return;
      }

      const currentPrice = parseWholeNumber(values.price);
      const priceChanged = currentPrice !== null && currentPrice !== initialPrice;
      const scope = values.priceChangeScope || undefined;
      const notificationMethod = values.notificationMethod || undefined;
      const notificationBody = values.notificationBody.trim();

      if (scope && !priceChanged) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["priceChangeScope"],
          message: "Price change scope can only be used when the price changes.",
        });
      }

      if (scope === "all_existing_confirmed") {
        if (!notificationMethod) {
          context.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["notificationMethod"],
            message: "Notification method is required for existing confirmed registrations.",
          });
        }

        if (!notificationBody) {
          context.addIssue({
            code: z.ZodIssueCode.custom,
            path: ["notificationBody"],
            message: "Notification body is required for existing confirmed registrations.",
          });
        }
      }

      if (scope === "new_registrations_only" && (notificationMethod || notificationBody)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["priceChangeScope"],
          message: "Notification settings are not allowed when the change affects only new registrations.",
        });
      }

      if (!scope && (notificationMethod || notificationBody)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["priceChangeScope"],
          message: "Notification settings require a selected price change scope.",
        });
      }
    });
}

function buildDefaultValues(mode: AdminEventFormMode, event?: AdminEventDetail): AdminEventFormValues {
  return {
    title: event?.title ?? "",
    description: event?.description ?? "",
    eventDate: event ? toDateTimeLocalInputValue(event.event_date) : "",
    location: event?.location ?? "",
    prefix: event?.prefix ?? "",
    price: event ? String(event.price) : "0",
    capacity: event?.capacity ? String(event.capacity) : "",
    overflowRule: event?.overflow_rule ?? "hard_rejection",
    customFields:
      event?.custom_fields
        .slice()
        .sort((left, right) => left.display_order - right.display_order)
        .map((field) => ({
          label: field.label,
          fieldType: field.field_type,
          isRequired: field.is_required,
          displayOrder: String(field.display_order),
        })) ?? [],
    priceChangeScope: "",
    notificationMethod: "",
    notificationBody: "",
  };
}

function buildCreatePayload(values: AdminEventFormValues): AdminEventCreateRequest {
  const eventDate = fromDateTimeLocalInputValue(values.eventDate);
  if (!eventDate) {
    throw new ApiError("Enter a valid date and time.", { code: "validation" });
  }

  const price = parseWholeNumber(values.price);
  if (price === null) {
    throw new ApiError("Enter a valid price.", { code: "validation" });
  }

  return {
    title: values.title.trim(),
    description: values.description.trim(),
    event_date: eventDate,
    location: values.location.trim(),
    prefix: values.prefix.trim(),
    price,
    capacity: values.capacity ? parsePositiveWholeNumber(values.capacity) : null,
    overflow_rule: values.overflowRule,
    custom_fields: values.customFields.map((field) => ({
      label: field.label.trim(),
      field_type: field.fieldType,
      is_required: field.isRequired,
      display_order: parsePositiveWholeNumber(field.displayOrder) ?? 1,
    })),
  };
}

function buildUpdatePayload(
  values: AdminEventFormValues,
  initialPrice: number,
): AdminEventUpdateRequest {
  const eventDate = fromDateTimeLocalInputValue(values.eventDate);
  if (!eventDate) {
    throw new ApiError("Enter a valid date and time.", { code: "validation" });
  }

  const price = parseWholeNumber(values.price);
  if (price === null) {
    throw new ApiError("Enter a valid price.", { code: "validation" });
  }

  const payload: AdminEventUpdateRequest = {
    title: values.title.trim(),
    description: values.description.trim(),
    event_date: eventDate,
    location: values.location.trim(),
    price,
    capacity: values.capacity ? parsePositiveWholeNumber(values.capacity) : null,
    custom_fields: values.customFields.map((field) => ({
      label: field.label.trim(),
      field_type: field.fieldType,
      is_required: field.isRequired,
      display_order: parsePositiveWholeNumber(field.displayOrder) ?? 1,
    })),
  };

  const priceChanged = price !== initialPrice;
  if (priceChanged && values.priceChangeScope) {
    payload.price_change_scope = values.priceChangeScope;
  }

  if (priceChanged && values.priceChangeScope === "all_existing_confirmed") {
    if (values.notificationMethod) {
      payload.notification_method = values.notificationMethod;
    }
    if (values.notificationBody.trim()) {
      payload.notification_body = values.notificationBody.trim();
    }
  }

  return payload;
}

function applyAdminEventFormApiErrors(
  error: unknown,
  setError: ReturnType<typeof useForm<AdminEventFormValues>>["setError"],
) {
  const apiError = error instanceof ApiError ? error : new ApiError("Could not save the event.", { code: "unknown" });
  const fieldErrors = apiError.fieldErrors;

  if (!fieldErrors || Object.keys(fieldErrors).length === 0) {
    setError("root", { type: "server", message: apiError.message });
    return;
  }

  let handledFieldError = false;

  for (const [field, messages] of Object.entries(fieldErrors)) {
    const message = messages[0];
    if (!message) {
      continue;
    }

    if (field === "title") {
      setError("title", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "description") {
      setError("description", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "event_date") {
      setError("eventDate", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "location") {
      setError("location", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "prefix") {
      setError("prefix", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "price") {
      setError("price", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "capacity") {
      setError("capacity", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "price_change_scope") {
      setError("priceChangeScope", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "notification_method") {
      setError("notificationMethod", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "notification_body") {
      setError("notificationBody", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    const customFieldMatch = field.match(/^custom_fields\.(\d+)\.(label|field_type|display_order)$/);
    if (customFieldMatch) {
      const index = Number(customFieldMatch[1]);
      const property = mapCustomFieldProperty(customFieldMatch[2]);
      const path = `customFields.${index}.${property}` as CustomFieldPath;
      setError(path, { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field.startsWith("custom_fields")) {
      setError("root", { type: "server", message });
      handledFieldError = true;
      continue;
    }

    if (field === "form") {
      setError("root", { type: "server", message });
      handledFieldError = true;
    }
  }

  if (!handledFieldError) {
    setError("root", { type: "server", message: apiError.message });
  }
}

function mapCustomFieldProperty(property: string): "label" | "fieldType" | "displayOrder" {
  if (property === "field_type") {
    return "fieldType";
  }
  if (property === "display_order") {
    return "displayOrder";
  }
  return "label";
}

function getNextDisplayOrder(fields: AdminEventFormValues["customFields"]): number {
  const maxDisplayOrder = fields.reduce((highest, field) => {
    const parsed = parsePositiveWholeNumber(field.displayOrder);
    return parsed && parsed > highest ? parsed : highest;
  }, 0);

  return maxDisplayOrder + 1;
}

function parseWholeNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!/^\d+$/.test(trimmed)) {
    return null;
  }

  return Number(trimmed);
}

function parsePositiveWholeNumber(value: string): number | null {
  const trimmed = value.trim();
  if (!/^[1-9]\d*$/.test(trimmed)) {
    return null;
  }

  return Number(trimmed);
}
