import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  adminRefundRequestListResponseSchema,
  adminRefundRequestUpdateRequestSchema,
  adminRefundRequestUpdateResponseSchema,
  type AdminRefundListParams,
  type AdminRefundRequestListResponse,
  type AdminRefundRequestUpdateRequest,
  type AdminRefundRequestUpdateResponse,
} from "../types/adminRefunds";

export async function listAdminRefundRequests(
  params: AdminRefundListParams,
  signal?: AbortSignal,
): Promise<AdminRefundRequestListResponse> {
  const response = await http.get("/admin/refund-requests", {
    params: buildRefundQueryParams(params),
    signal,
  });

  return parseApiResponse(
    adminRefundRequestListResponseSchema,
    response.data,
    "the admin refund request list",
  );
}

export async function updateAdminRefundRequest(
  refundRequestId: string,
  payload: AdminRefundRequestUpdateRequest,
): Promise<AdminRefundRequestUpdateResponse> {
  const requestPayload = parseApiResponse(
    adminRefundRequestUpdateRequestSchema,
    payload,
    "the refund update request",
  );

  const response = await http.patch(
    `/admin/refund-requests/${refundRequestId}`,
    requestPayload,
  );

  return parseApiResponse(
    adminRefundRequestUpdateResponseSchema,
    response.data,
    "the updated refund request",
  );
}

function buildRefundQueryParams(params: AdminRefundListParams): URLSearchParams {
  const searchParams = new URLSearchParams();

  if (params.status) {
    searchParams.set("status", params.status);
  }

  if (params.eventId?.trim()) {
    searchParams.set("event_id", params.eventId.trim());
  }

  if (params.regId?.trim()) {
    searchParams.set("reg_id", params.regId.trim());
  }

  return searchParams;
}
