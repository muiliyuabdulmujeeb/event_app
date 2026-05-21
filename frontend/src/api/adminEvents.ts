import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  adminEventCreateRequestSchema,
  adminEventDetailSchema,
  adminEventListResponseSchema,
  adminEventOverflowRuleUpdateRequestSchema,
  adminEventOverflowRuleUpdateResponseSchema,
  adminEventStateUpdateRequestSchema,
  adminEventUpdateRequestSchema,
  type AdminEventCreateRequest,
  type AdminEventDetail,
  type AdminEventListResponse,
  type AdminEventOverflowRuleUpdateRequest,
  type AdminEventOverflowRuleUpdateResponse,
  type AdminEventStateUpdateRequest,
  type AdminEventUpdateRequest,
} from "../types/adminEvents";

export async function listAdminEvents(signal?: AbortSignal): Promise<AdminEventListResponse> {
  const response = await http.get("/admin/events", { signal });
  return parseApiResponse(adminEventListResponseSchema, response.data, "the admin event list");
}

export async function getAdminEventDetail(
  eventId: string,
  signal?: AbortSignal,
): Promise<AdminEventDetail> {
  const response = await http.get(`/admin/events/${eventId}`, { signal });
  return parseApiResponse(
    adminEventDetailSchema,
    response.data,
    "the admin event details",
  );
}

export async function createAdminEvent(
  payload: AdminEventCreateRequest,
): Promise<AdminEventDetail> {
  const requestPayload = parseApiResponse(
    adminEventCreateRequestSchema,
    payload,
    "the event creation request",
  );

  const response = await http.post("/admin/events", requestPayload);
  return parseApiResponse(
    adminEventDetailSchema,
    response.data,
    "the created event details",
  );
}

export async function updateAdminEvent(
  eventId: string,
  payload: AdminEventUpdateRequest,
): Promise<AdminEventDetail> {
  const requestPayload = parseApiResponse(
    adminEventUpdateRequestSchema,
    payload,
    "the event update request",
  );

  const response = await http.patch(`/admin/events/${eventId}`, requestPayload);
  return parseApiResponse(
    adminEventDetailSchema,
    response.data,
    "the updated event details",
  );
}

export async function updateAdminEventState(
  eventId: string,
  payload: AdminEventStateUpdateRequest,
): Promise<AdminEventDetail> {
  const requestPayload = parseApiResponse(
    adminEventStateUpdateRequestSchema,
    payload,
    "the event state update request",
  );

  const response = await http.patch(`/admin/events/${eventId}/state`, requestPayload);
  return parseApiResponse(
    adminEventDetailSchema,
    response.data,
    "the updated event state",
  );
}

export async function updateAdminEventOverflowRule(
  eventId: string,
  payload: AdminEventOverflowRuleUpdateRequest,
): Promise<AdminEventOverflowRuleUpdateResponse> {
  const requestPayload = parseApiResponse(
    adminEventOverflowRuleUpdateRequestSchema,
    payload,
    "the overflow rule update request",
  );

  const response = await http.patch(`/admin/events/${eventId}/overflow-rule`, requestPayload);
  return parseApiResponse(
    adminEventOverflowRuleUpdateResponseSchema,
    response.data,
    "the overflow rule update result",
  );
}
