import { z } from "zod";

import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  adminStaffAccessConfigResponseSchema,
  adminStaffAccessModeUpdateRequestSchema,
  adminStaffAccountDetailSchema,
  adminStaffAccountSummarySchema,
  adminStaffAccountUpdateRequestSchema,
  adminStaffEventAccessAddRequestSchema,
  type AdminStaffAccessConfigResponse,
  type AdminStaffAccessModeUpdateRequest,
  type AdminStaffAccountDetail,
  type AdminStaffAccountSummary,
  type AdminStaffAccountUpdateRequest,
  type AdminStaffEventAccessAddRequest,
} from "../types/adminStaff";

const adminStaffAccountListSchema = z.array(adminStaffAccountSummarySchema);

export async function listAdminStaffAccounts(
  signal?: AbortSignal,
): Promise<AdminStaffAccountSummary[]> {
  const response = await http.get("/admin/staff", { signal });
  return parseApiResponse(
    adminStaffAccountListSchema,
    response.data,
    "the admin staff list",
  );
}

export async function getAdminStaffAccount(
  staffId: string,
  signal?: AbortSignal,
): Promise<AdminStaffAccountDetail> {
  const response = await http.get(`/admin/staff/${staffId}`, { signal });
  return parseApiResponse(
    adminStaffAccountDetailSchema,
    response.data,
    "the staff account details",
  );
}

export async function updateAdminStaffAccount(
  staffId: string,
  payload: AdminStaffAccountUpdateRequest,
): Promise<AdminStaffAccountDetail> {
  const requestPayload = parseApiResponse(
    adminStaffAccountUpdateRequestSchema,
    payload,
    "the staff account update request",
  );

  const response = await http.patch(`/admin/staff/${staffId}`, requestPayload);
  return parseApiResponse(
    adminStaffAccountDetailSchema,
    response.data,
    "the updated staff account details",
  );
}

export async function setAdminStaffAccessMode(
  staffId: string,
  payload: AdminStaffAccessModeUpdateRequest,
): Promise<AdminStaffAccessConfigResponse> {
  const requestPayload = parseApiResponse(
    adminStaffAccessModeUpdateRequestSchema,
    payload,
    "the staff access mode request",
  );

  const response = await http.put(`/admin/staff/${staffId}/access`, requestPayload);
  return parseApiResponse(
    adminStaffAccessConfigResponseSchema,
    response.data,
    "the updated staff access configuration",
  );
}

export async function addAdminStaffEventAccess(
  staffId: string,
  payload: AdminStaffEventAccessAddRequest,
): Promise<AdminStaffAccessConfigResponse> {
  const requestPayload = parseApiResponse(
    adminStaffEventAccessAddRequestSchema,
    payload,
    "the staff event-access request",
  );

  const response = await http.post(`/admin/staff/${staffId}/access/events`, requestPayload);
  return parseApiResponse(
    adminStaffAccessConfigResponseSchema,
    response.data,
    "the updated staff selected-event access",
  );
}

export async function removeAdminStaffEventAccess(
  staffId: string,
  eventId: string,
): Promise<AdminStaffAccessConfigResponse> {
  const response = await http.delete(`/admin/staff/${staffId}/access/events/${eventId}`);
  return parseApiResponse(
    adminStaffAccessConfigResponseSchema,
    response.data,
    "the updated staff selected-event access",
  );
}
