import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  publicEventDetailSchema,
  publicEventListResponseSchema,
  type PublicEventDetail,
  type PublicEventListResponse,
} from "../types/events";

type ListPublicEventsParams = {
  search?: string;
  isFree?: boolean | null;
};

export async function listPublicEvents(
  params: ListPublicEventsParams,
  signal?: AbortSignal,
): Promise<PublicEventListResponse> {
  const response = await http.get("/events", {
    params: {
      search: params.search || undefined,
      is_free: params.isFree ?? undefined,
    },
    signal,
  });

  return parseApiResponse(publicEventListResponseSchema, response.data, "the public event list");
}

export async function getPublicEventDetail(
  eventId: string,
  signal?: AbortSignal,
): Promise<PublicEventDetail> {
  const response = await http.get(`/events/${eventId}`, { signal });
  return parseApiResponse(publicEventDetailSchema, response.data, "the event details");
}
