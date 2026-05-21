import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  singleRegistrationRequestSchema,
  singleRegistrationResponseSchema,
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
