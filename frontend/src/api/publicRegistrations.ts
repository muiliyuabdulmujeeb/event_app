import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  batchRegistrationRequestSchema,
  batchRegistrationResponseSchema,
  singleRegistrationRequestSchema,
  singleRegistrationResponseSchema,
  type BatchRegistrationRequest,
  type BatchRegistrationResponse,
  type SingleRegistrationRequest,
  type SingleRegistrationResponse,
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
