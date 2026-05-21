import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  batchRegistrationRequestSchema,
  batchRegistrationResponseSchema,
  registrationPaymentInitializationResponseSchema,
  refundRequestCreateRequestSchema,
  refundRequestCreateResponseSchema,
  registrationCancellationRequestSchema,
  registrationCancellationResponseSchema,
  registrationLookupResponseSchema,
  singleRegistrationRequestSchema,
  singleRegistrationResponseSchema,
  userNotificationSeenResponseSchema,
  type BatchRegistrationRequest,
  type BatchRegistrationResponse,
  type RegistrationPaymentInitializationResponse,
  type RefundRequestCreateRequest,
  type RefundRequestCreateResponse,
  type RegistrationCancellationRequest,
  type RegistrationCancellationResponse,
  type RegistrationLookupResponse,
  type SingleRegistrationRequest,
  type SingleRegistrationResponse,
  type UserNotificationSeenResponse,
} from "../types/registrations";

export async function createSingleRegistration(
  eventId: string,
  payload: SingleRegistrationRequest,
  signal?: AbortSignal,
): Promise<SingleRegistrationResponse> {
  const requestPayload = parseApiResponse(
    singleRegistrationRequestSchema,
    payload,
    "the registration submission",
  );

  const response = await http.post(`/register/${eventId}`, requestPayload, { signal });
  return parseApiResponse(
    singleRegistrationResponseSchema,
    response.data,
    "the registration confirmation",
  );
}

export async function createBatchRegistration(
  eventId: string,
  payload: BatchRegistrationRequest,
  signal?: AbortSignal,
): Promise<BatchRegistrationResponse> {
  const requestPayload = parseApiResponse(
    batchRegistrationRequestSchema,
    payload,
    "the batch registration submission",
  );

  const response = await http.post(`/register/${eventId}/batch`, requestPayload, { signal });
  return parseApiResponse(
    batchRegistrationResponseSchema,
    response.data,
    "the batch registration confirmation",
  );
}

export async function lookupRegistration(
  regId: string,
  signal?: AbortSignal,
): Promise<RegistrationLookupResponse> {
  const response = await http.get("/registrations/lookup", {
    params: { reg_id: regId },
    signal,
  });

  return parseApiResponse(
    registrationLookupResponseSchema,
    response.data,
    "the registration lookup result",
  );
}

export async function markRegistrationNotificationSeen(
  notificationId: string,
): Promise<UserNotificationSeenResponse> {
  const response = await http.patch(`/registrations/notifications/${notificationId}/seen`);
  return parseApiResponse(
    userNotificationSeenResponseSchema,
    response.data,
    "the notification update",
  );
}

export async function cancelRegistration(
  regId: string,
  payload: RegistrationCancellationRequest,
): Promise<RegistrationCancellationResponse> {
  const requestPayload = parseApiResponse(
    registrationCancellationRequestSchema,
    payload,
    "the registration cancellation request",
  );

  const response = await http.patch(`/registrations/${regId}/cancel`, requestPayload);
  return parseApiResponse(
    registrationCancellationResponseSchema,
    response.data,
    "the registration cancellation result",
  );
}

export async function createRefundRequest(
  regId: string,
  payload: RefundRequestCreateRequest,
): Promise<RefundRequestCreateResponse> {
  const requestPayload = parseApiResponse(
    refundRequestCreateRequestSchema,
    payload,
    "the refund request submission",
  );

  const response = await http.post(`/registrations/${regId}/refund-requests`, requestPayload);
  return parseApiResponse(
    refundRequestCreateResponseSchema,
    response.data,
    "the refund request result",
  );
}

export async function initializeRegistrationPayment(
  regId: string,
): Promise<RegistrationPaymentInitializationResponse> {
  const response = await http.post(`/registrations/${regId}/payments/initialize`);
  return parseApiResponse(
    registrationPaymentInitializationResponseSchema,
    response.data,
    "the payment initialization result",
  );
}
