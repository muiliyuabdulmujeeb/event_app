import { useEffect, useMemo, useState } from "react";
import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link, useParams } from "react-router-dom";
import { z } from "zod";

import {
  addAdminStaffEventAccess,
  getAdminStaffAccount,
  removeAdminStaffEventAccess,
  setAdminStaffAccessMode,
  updateAdminStaffAccount,
} from "../api/adminStaff";
import { listAdminEvents } from "../api/adminEvents";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { AdminEventListResponse } from "../types/adminEvents";
import {
  staffAccessModeSchema,
  staffRoleSchema,
  type AdminStaffAccessConfigResponse,
  type AdminStaffAccessModeUpdateRequest,
  type AdminStaffAccountDetail,
  type AdminStaffAccountSummary,
  type AdminStaffAccountUpdateRequest,
  type StaffAccessMode,
  type StaffRole,
} from "../types/adminStaff";

const accountFormSchema = z.object({
  email: z.string().trim().email("Enter a valid email address."),
  role: staffRoleSchema,
  isActive: z.boolean(),
});

const accessModeFormSchema = z.object({
  mode: staffAccessModeSchema,
});

const selectedEventFormSchema = z.object({
  eventId: z.string().trim().min(1, "Select an event to add."),
});

type AccountFormValues = z.infer<typeof accountFormSchema>;
type AccessModeFormValues = z.infer<typeof accessModeFormSchema>;
type SelectedEventFormValues = z.infer<typeof selectedEventFormSchema>;

export function AdminStaffDetailPage() {
  const { staffId } = useParams<{ staffId: string }>();
  const queryClient = useQueryClient();
  const [updateMessage, setUpdateMessage] = useState<string | null>(null);

  if (!staffId) {
    return (
      <ErrorState
        title="Staff account unavailable"
        message="The staff account identifier is missing from the current route."
      />
    );
  }

  const detailQuery = useQuery<AdminStaffAccountDetail, ApiError>({
    queryKey: queryKeys.adminStaff.detail(staffId),
    queryFn: ({ signal }) => getAdminStaffAccount(staffId, signal),
  });

  const eventsQuery = useQuery<AdminEventListResponse, ApiError>({
    queryKey: queryKeys.adminEvents.all,
    queryFn: ({ signal }) => listAdminEvents(signal),
  });

  const accountForm = useForm<AccountFormValues>({
    resolver: zodResolver(accountFormSchema),
    defaultValues: {
      email: "",
      role: "staff",
      isActive: true,
    },
  });

  const accessModeForm = useForm<AccessModeFormValues>({
    resolver: zodResolver(accessModeFormSchema),
    defaultValues: {
      mode: "all_events",
    },
  });

  const selectedEventForm = useForm<SelectedEventFormValues>({
    resolver: zodResolver(selectedEventFormSchema),
    defaultValues: {
      eventId: "",
    },
  });

  useEffect(() => {
    if (!detailQuery.data) {
      return;
    }

    accountForm.reset({
      email: detailQuery.data.email,
      role: detailQuery.data.role,
      isActive: detailQuery.data.is_active,
    });
    accessModeForm.reset({
      mode: detailQuery.data.access_mode,
    });
  }, [accountForm, accessModeForm, detailQuery.data]);

  const availableEvents = useMemo(() => {
    if (!detailQuery.data || !eventsQuery.data) {
      return [];
    }

    const selectedEventIds = new Set(detailQuery.data.selected_events.map((event) => event.id));
    return eventsQuery.data.events.filter((event) => !selectedEventIds.has(event.id));
  }, [detailQuery.data, eventsQuery.data]);

  const accountMutation = useMutation<
    AdminStaffAccountDetail,
    ApiError,
    AdminStaffAccountUpdateRequest
  >({
    mutationFn: (payload) => updateAdminStaffAccount(staffId, payload),
    onSuccess: (response) => {
      queryClient.setQueryData(queryKeys.adminStaff.detail(staffId), response);
      queryClient.setQueryData<AdminStaffAccountSummary[] | undefined>(
        queryKeys.adminStaff.all,
        (current) =>
          current?.map((account) =>
            account.id === response.id
              ? {
                  ...account,
                  email: response.email,
                  role: response.role,
                  is_active: response.is_active,
                }
              : account,
          ),
      );
      setUpdateMessage("Staff account settings were updated.");
    },
  });

  const accessModeMutation = useMutation<
    AdminStaffAccessConfigResponse,
    ApiError,
    AdminStaffAccessModeUpdateRequest
  >({
    mutationFn: (payload) => setAdminStaffAccessMode(staffId, payload),
    onSuccess: (response) => {
      queryClient.setQueryData<AdminStaffAccountDetail | undefined>(
        queryKeys.adminStaff.detail(staffId),
        (current) => mergeAccessConfig(current, response),
      );
      selectedEventForm.reset({ eventId: "" });
      setUpdateMessage(
        response.access_mode === "all_events"
          ? "Access mode updated to all events."
          : "Access mode updated to selected events.",
      );
    },
  });

  const addEventAccessMutation = useMutation<
    AdminStaffAccessConfigResponse,
    ApiError,
    string
  >({
    mutationFn: (eventId) => addAdminStaffEventAccess(staffId, { event_id: eventId }),
    onSuccess: (response) => {
      queryClient.setQueryData<AdminStaffAccountDetail | undefined>(
        queryKeys.adminStaff.detail(staffId),
        (current) => mergeAccessConfig(current, response),
      );
      selectedEventForm.reset({ eventId: "" });
      setUpdateMessage("Selected-event access was updated.");
    },
  });

  const removeEventAccessMutation = useMutation<
    AdminStaffAccessConfigResponse,
    ApiError,
    string
  >({
    mutationFn: (eventId) => removeAdminStaffEventAccess(staffId, eventId),
    onSuccess: (response) => {
      queryClient.setQueryData<AdminStaffAccountDetail | undefined>(
        queryKeys.adminStaff.detail(staffId),
        (current) => mergeAccessConfig(current, response),
      );
      setUpdateMessage("Selected-event access was updated.");
    },
  });

  useEffect(() => {
    if (
      detailQuery.data?.access_mode === "selected_events" &&
      !selectedEventForm.getValues("eventId") &&
      availableEvents.length > 0
    ) {
      selectedEventForm.setValue("eventId", availableEvents[0].id);
    }
  }, [availableEvents, detailQuery.data?.access_mode, selectedEventForm]);

  if (detailQuery.isPending) {
    return <LoadingState label="Loading staff account..." />;
  }

  if (detailQuery.isError) {
    return (
      <ErrorState
        title={detailQuery.error.code === "notFound" ? "Staff account not found" : "Could not load this staff account"}
        message={detailQuery.error.message}
      />
    );
  }

  const account = detailQuery.data;
  const removingEventId = removeEventAccessMutation.isPending
    ? removeEventAccessMutation.variables ?? null
    : null;

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Staff account details"
          description="Update role and activation settings, then control whether this account can access all events or only a selected event list."
        />
        <div className="panel__actions">
          <Link to="/admin/staff" className="button-link">
            Back to staff list
          </Link>
        </div>
      </section>

      {updateMessage ? (
        <div className="action-feedback" role="status">
          <p className="action-feedback__title">{updateMessage}</p>
        </div>
      ) : null}

      <section className="metric-grid">
        <MetricCard label="Role" value={formatRole(account.role)} />
        <MetricCard label="Status" value={account.is_active ? "Active" : "Disabled"} />
        <MetricCard label="Access mode" value={formatAccessMode(account.access_mode)} />
        <MetricCard label="Selected events" value={account.selected_events.length} />
      </section>

      <section className="event-detail-grid">
        <article className="detail-card">
          <h2 className="detail-card__title">Account metadata</h2>
          <dl className="detail-list">
            <div>
              <dt>Account ID</dt>
              <dd>{account.id}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatDateTime(account.created_at)}</dd>
            </div>
          </dl>
        </article>

        <article className="detail-card">
          <h2 className="detail-card__title">Current access summary</h2>
          <dl className="detail-list">
            <div>
              <dt>Access mode</dt>
              <dd>{formatAccessMode(account.access_mode)}</dd>
            </div>
            <div>
              <dt>Selected events</dt>
              <dd>{account.selected_events.length}</dd>
            </div>
          </dl>
        </article>
      </section>

      <section className="panel">
        <div className="section-header">
          <div>
            <h2 className="section-title">Account settings</h2>
            <p className="section-note">
              Only the backend-supported account fields are editable here.
            </p>
          </div>
        </div>

        {accountForm.formState.errors.root?.message ? (
          <div className="form-alert" role="alert">
            {accountForm.formState.errors.root.message}
          </div>
        ) : null}

        <form
          className="auth-form"
          noValidate
          onSubmit={accountForm.handleSubmit(async (values) => {
            accountForm.clearErrors("root");

            const payload = buildAccountUpdatePayload(account, values);
            if (!payload) {
              accountForm.setError("root", {
                type: "manual",
                message: "No account changes to save.",
              });
              return;
            }

            try {
              await accountMutation.mutateAsync(payload);
            } catch (error) {
              applySimpleFormErrors(error, accountForm.setError, {
                email: "email",
                role: "role",
                is_active: "isActive",
              });
            }
          })}
        >
          <div className="form-grid">
            <div className="form-field">
              <label className="form-label" htmlFor="admin-staff-email">
                Email address
              </label>
              <input
                id="admin-staff-email"
                type="email"
                className="form-input"
                aria-invalid={accountForm.formState.errors.email ? "true" : "false"}
                {...accountForm.register("email")}
              />
              {accountForm.formState.errors.email ? (
                <p className="form-error">{accountForm.formState.errors.email.message}</p>
              ) : null}
            </div>

            <div className="form-field">
              <label className="form-label" htmlFor="admin-staff-role">
                Role
              </label>
              <select
                id="admin-staff-role"
                className="form-input"
                aria-invalid={accountForm.formState.errors.role ? "true" : "false"}
                {...accountForm.register("role")}
              >
                <option value="staff">Staff</option>
                <option value="admin">Admin</option>
              </select>
              {accountForm.formState.errors.role ? (
                <p className="form-error">{accountForm.formState.errors.role.message}</p>
              ) : null}
            </div>
          </div>

          <div className="checkbox-card checkbox-card--neutral">
            <label className="checkbox-field" htmlFor="admin-staff-is-active">
              <input
                id="admin-staff-is-active"
                type="checkbox"
                className="checkbox-input"
                {...accountForm.register("isActive")}
              />
              <span>Account is active and allowed to authenticate.</span>
            </label>
          </div>

          <div className="panel__actions">
            <button
              type="submit"
              className="button-link button-link--primary"
              disabled={accountMutation.isPending}
            >
              {accountMutation.isPending ? "Saving..." : "Save account settings"}
            </button>
          </div>
        </form>
      </section>

      <section className="event-detail-grid">
        <article className="detail-card">
          <div className="section-header">
            <div>
              <h2 className="detail-card__title">Access mode</h2>
              <p className="section-note">
                Changing to all-events access clears any selected-event entries on the backend.
              </p>
            </div>
          </div>

          {accessModeForm.formState.errors.root?.message ? (
            <div className="form-alert" role="alert">
              {accessModeForm.formState.errors.root.message}
            </div>
          ) : null}

          <form
            className="auth-form"
            noValidate
            onSubmit={accessModeForm.handleSubmit(async (values) => {
              accessModeForm.clearErrors("root");

              if (values.mode === account.access_mode) {
                accessModeForm.setError("root", {
                  type: "manual",
                  message: "Access mode is already set to that value.",
                });
                return;
              }

              try {
                await accessModeMutation.mutateAsync({ mode: values.mode });
              } catch (error) {
                applySimpleFormErrors(error, accessModeForm.setError, {
                  mode: "mode",
                });
              }
            })}
          >
            <div className="form-field">
              <label className="form-label" htmlFor="admin-staff-access-mode">
                Access mode
              </label>
              <select
                id="admin-staff-access-mode"
                className="form-input"
                aria-invalid={accessModeForm.formState.errors.mode ? "true" : "false"}
                {...accessModeForm.register("mode")}
              >
                <option value="all_events">All events</option>
                <option value="selected_events">Selected events</option>
              </select>
              {accessModeForm.formState.errors.mode ? (
                <p className="form-error">{accessModeForm.formState.errors.mode.message}</p>
              ) : null}
            </div>

            <div className="panel__actions">
              <button
                type="submit"
                className="button-link button-link--primary"
                disabled={accessModeMutation.isPending}
              >
                {accessModeMutation.isPending ? "Updating..." : "Update access mode"}
              </button>
            </div>
          </form>
        </article>

        <article className="detail-card">
          <div className="section-header">
            <div>
              <h2 className="detail-card__title">Selected-event access</h2>
              <p className="section-note">
                Add or remove events only when the account is in selected-events mode.
              </p>
            </div>
          </div>

          {account.access_mode !== "selected_events" ? (
            <EmptyState
              title="Selected-event access is disabled"
              description="Switch this account to selected-events mode before assigning or removing event-specific access."
            />
          ) : (
            <div className="page-stack page-stack--compact">
              {selectedEventForm.formState.errors.root?.message ? (
                <div className="form-alert" role="alert">
                  {selectedEventForm.formState.errors.root.message}
                </div>
              ) : null}

              {eventsQuery.isPending ? <LoadingState label="Loading available events..." /> : null}

              {eventsQuery.isError ? (
                <ErrorState
                  title="Could not load the event list"
                  message={eventsQuery.error.message}
                />
              ) : null}

              {!eventsQuery.isPending && !eventsQuery.isError ? (
                <form
                  className="auth-form"
                  noValidate
                  onSubmit={selectedEventForm.handleSubmit(async (values) => {
                    selectedEventForm.clearErrors("root");

                    try {
                      await addEventAccessMutation.mutateAsync(values.eventId);
                    } catch (error) {
                      applySimpleFormErrors(error, selectedEventForm.setError, {
                        event_id: "eventId",
                      });
                    }
                  })}
                >
                  <div className="form-field">
                    <label className="form-label" htmlFor="admin-staff-event-select">
                      Add event access
                    </label>
                    <select
                      id="admin-staff-event-select"
                      className="form-input"
                      aria-invalid={selectedEventForm.formState.errors.eventId ? "true" : "false"}
                      disabled={availableEvents.length === 0}
                      {...selectedEventForm.register("eventId")}
                    >
                      {availableEvents.length === 0 ? (
                        <option value="">No more events available to add</option>
                      ) : null}
                      {availableEvents.map((event) => (
                        <option key={event.id} value={event.id}>
                          {event.title}
                        </option>
                      ))}
                    </select>
                    {selectedEventForm.formState.errors.eventId ? (
                      <p className="form-error">{selectedEventForm.formState.errors.eventId.message}</p>
                    ) : null}
                  </div>

                  <div className="panel__actions">
                    <button
                      type="submit"
                      className="button-link button-link--primary"
                      disabled={addEventAccessMutation.isPending || availableEvents.length === 0}
                    >
                      {addEventAccessMutation.isPending ? "Adding..." : "Add event access"}
                    </button>
                  </div>
                </form>
              ) : null}

              {account.selected_events.length === 0 ? (
                <EmptyState
                  title="No selected events assigned"
                  description="Add event-specific access from the list above to limit this account to chosen events."
                />
              ) : (
                <div className="selected-event-list">
                  {account.selected_events.map((event) => (
                    <article className="selected-event-item" key={event.id}>
                      <div className="selected-event-item__content">
                        <h3 className="selected-event-item__title">{event.title}</h3>
                        <p className="selected-event-item__meta">{event.id}</p>
                      </div>
                      <div className="panel__actions">
                        <Link to={`/admin/events/${event.id}/edit`} className="button-link">
                          View event
                        </Link>
                        <button
                          type="button"
                          className="button-link"
                          onClick={() => {
                            selectedEventForm.clearErrors("root");
                            removeEventAccessMutation.mutate(event.id, {
                              onError: (error) => {
                                selectedEventForm.setError("root", {
                                  type: "server",
                                  message: error.message,
                                });
                              },
                            });
                          }}
                          disabled={removingEventId === event.id}
                        >
                          {removingEventId === event.id ? "Removing..." : "Remove access"}
                        </button>
                      </div>
                    </article>
                  ))}
                </div>
              )}
            </div>
          )}
        </article>
      </section>
    </div>
  );
}

function buildAccountUpdatePayload(
  current: AdminStaffAccountDetail,
  values: AccountFormValues,
): AdminStaffAccountUpdateRequest | null {
  const payload: AdminStaffAccountUpdateRequest = {};

  if (values.email.trim() !== current.email) {
    payload.email = values.email.trim();
  }

  if (values.role !== current.role) {
    payload.role = values.role;
  }

  if (values.isActive !== current.is_active) {
    payload.is_active = values.isActive;
  }

  return Object.keys(payload).length > 0 ? payload : null;
}

function mergeAccessConfig(
  current: AdminStaffAccountDetail | undefined,
  response: AdminStaffAccessConfigResponse,
): AdminStaffAccountDetail | undefined {
  if (!current) {
    return current;
  }

  return {
    ...current,
    access_mode: response.access_mode,
    selected_events: response.selected_events,
  };
}

function applySimpleFormErrors<TFieldName extends string>(
  error: unknown,
  setError: (name: TFieldName | "root", error: { type: string; message: string }) => void,
  mappings: Record<string, TFieldName>,
) {
  const apiError =
    error instanceof ApiError
      ? error
      : new ApiError("Could not save the changes.", { code: "unknown" });

  if (!apiError.fieldErrors || Object.keys(apiError.fieldErrors).length === 0) {
    setError("root", { type: "server", message: apiError.message });
    return;
  }

  let handledFieldError = false;

  for (const [field, messages] of Object.entries(apiError.fieldErrors)) {
    const message = messages[0];
    if (!message) {
      continue;
    }

    const mappedField = mappings[field];
    if (mappedField) {
      setError(mappedField, { type: "server", message });
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

function MetricCard({ label, value }: { label: string; value: number | string }) {
  return (
    <article className="metric-card">
      <p className="metric-card__label">{label}</p>
      <p className="metric-card__value">{value}</p>
    </article>
  );
}

function formatRole(role: StaffRole): string {
  return role === "admin" ? "Admin" : "Staff";
}

function formatAccessMode(mode: StaffAccessMode): string {
  return mode === "all_events" ? "All events" : "Selected events";
}
