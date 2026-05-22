import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  adminNotificationCreateRequestSchema,
  adminNotificationDispatchResponseSchema,
  type AdminNotificationCreateRequest,
  type AdminNotificationDispatchResponse,
} from "../types/adminNotifications";

export async function dispatchAdminNotification(
  payload: AdminNotificationCreateRequest,
): Promise<AdminNotificationDispatchResponse> {
  const requestPayload = parseApiResponse(
    adminNotificationCreateRequestSchema,
    payload,
    "the admin notification request",
  );

  const response = await http.post("/admin/notifications", requestPayload);
  return parseApiResponse(
    adminNotificationDispatchResponseSchema,
    response.data,
    "the admin notification result",
  );
}
