import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  staffCheckInResponseSchema,
  staffNotificationListResponseSchema,
  staffNotificationReadResponseSchema,
  staffRegistrationSearchResponseSchema,
  type StaffCheckInResponse,
  type StaffNotificationListResponse,
  type StaffNotificationReadResponse,
  type StaffRegistrationSearchResponse,
} from "../types/staff";

type StaffRegistrationSearchParams = {
  regId?: string;
  email?: string;
};

export async function searchStaffRegistrations(
  params: StaffRegistrationSearchParams,
  signal?: AbortSignal,
): Promise<StaffRegistrationSearchResponse> {
  const response = await http.get("/staff/registrations", {
    params: {
      reg_id: params.regId,
      email: params.email,
    },
    signal,
  });

  return parseApiResponse(
    staffRegistrationSearchResponseSchema,
    response.data,
    "the staff registration search result",
  );
}

export async function checkInRegistration(regId: string): Promise<StaffCheckInResponse> {
  const response = await http.patch(`/staff/registrations/${regId}/checkin`);
  return parseApiResponse(
    staffCheckInResponseSchema,
    response.data,
    "the check-in update",
  );
}

export async function uncheckInRegistration(regId: string): Promise<StaffCheckInResponse> {
  const response = await http.patch(`/staff/registrations/${regId}/uncheckin`);
  return parseApiResponse(
    staffCheckInResponseSchema,
    response.data,
    "the reverse check-in update",
  );
}

export async function listStaffNotifications(
  signal?: AbortSignal,
): Promise<StaffNotificationListResponse> {
  const response = await http.get("/staff/notifications", { signal });
  return parseApiResponse(
    staffNotificationListResponseSchema,
    response.data,
    "the unread staff notifications",
  );
}

export async function markStaffNotificationRead(
  notificationId: string,
): Promise<StaffNotificationReadResponse> {
  const response = await http.patch(`/staff/notifications/${notificationId}/read`);
  return parseApiResponse(
    staffNotificationReadResponseSchema,
    response.data,
    "the staff notification update",
  );
}
