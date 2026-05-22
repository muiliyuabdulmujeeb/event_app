import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  adminAnalyticsSummaryResponseSchema,
  adminAnalyticsRegistrationsResponseSchema,
  type AdminAnalyticsDownloadParams,
  type AdminAnalyticsRegistrationsParams,
  type AdminAnalyticsRegistrationsResponse,
  type AdminAnalyticsSummaryParams,
  type AdminAnalyticsSummaryResponse,
} from "../types/adminAnalytics";

const DEFAULT_PAGE_SIZE = 50;

export async function getAdminAnalyticsSummary(
  params: AdminAnalyticsSummaryParams,
  signal?: AbortSignal,
): Promise<AdminAnalyticsSummaryResponse> {
  const response = await http.get("/admin/analytics", {
    params: buildAnalyticsSummarySearchParams(params),
    signal,
  });

  return parseApiResponse(
    adminAnalyticsSummaryResponseSchema,
    response.data,
    "the admin analytics summary",
  );
}

export async function getAdminAnalyticsRegistrations(
  params: AdminAnalyticsRegistrationsParams,
  signal?: AbortSignal,
): Promise<AdminAnalyticsRegistrationsResponse> {
  const response = await http.get("/admin/analytics/registrations", {
    params: buildAnalyticsRegistrationsSearchParams(params),
    signal,
  });

  return parseApiResponse(
    adminAnalyticsRegistrationsResponseSchema,
    response.data,
    "the admin registrations table",
  );
}

export async function downloadAdminAnalytics(
  params: AdminAnalyticsDownloadParams,
): Promise<{ blob: Blob; filename: string; contentType: string }> {
  const response = await http.get("/admin/analytics/download", {
    params: buildAnalyticsDownloadSearchParams(params),
    responseType: "blob",
  });

  return {
    blob: response.data,
    filename: extractFilename(response.headers["content-disposition"]) ?? defaultFilenameForFormat(params.format),
    contentType:
      typeof response.headers["content-type"] === "string"
        ? response.headers["content-type"]
        : "application/octet-stream",
  };
}

function buildAnalyticsSummarySearchParams(
  params: AdminAnalyticsSummaryParams,
): URLSearchParams {
  const searchParams = new URLSearchParams();

  for (const eventId of params.event_ids ?? []) {
    if (eventId.trim()) {
      searchParams.append("event_ids", eventId.trim());
    }
  }

  appendText(searchParams, "date_from", params.date_from);
  appendText(searchParams, "date_to", params.date_to);

  return searchParams;
}

function buildAnalyticsRegistrationsSearchParams(
  params: AdminAnalyticsRegistrationsParams,
): URLSearchParams {
  const searchParams = new URLSearchParams();

  for (const eventId of params.event_ids ?? []) {
    if (eventId.trim()) {
      searchParams.append("event_ids", eventId.trim());
    }
  }

  appendText(searchParams, "date_from", params.date_from);
  appendText(searchParams, "date_to", params.date_to);
  appendText(searchParams, "state", params.state);
  appendBoolean(searchParams, "is_checked_in", params.is_checked_in);
  appendText(searchParams, "email", params.email);
  appendText(searchParams, "first_name", params.first_name);
  appendText(searchParams, "last_name", params.last_name);
  appendBoolean(searchParams, "is_batch", params.is_batch);
  appendText(searchParams, "payment_status", params.payment_status);
  appendText(searchParams, "paid_from", params.paid_from);
  appendText(searchParams, "paid_to", params.paid_to);
  appendNumber(searchParams, "amount_min", params.amount_min);
  appendNumber(searchParams, "amount_max", params.amount_max);

  for (const customFieldFilter of params.custom_field ?? []) {
    const trimmed = customFieldFilter.trim();
    if (trimmed) {
      searchParams.append("custom_field", trimmed);
    }
  }

  const page = params.page && params.page > 0 ? Math.floor(params.page) : 1;
  const pageSize =
    params.page_size && params.page_size > 0
      ? Math.min(Math.floor(params.page_size), DEFAULT_PAGE_SIZE)
      : DEFAULT_PAGE_SIZE;

  searchParams.set("page", String(page));
  searchParams.set("page_size", String(pageSize));
  searchParams.set("sort_by", params.sort_by?.trim() || "registered_at");
  searchParams.set("sort_order", params.sort_order ?? "desc");

  return searchParams;
}

function buildAnalyticsDownloadSearchParams(
  params: AdminAnalyticsDownloadParams,
): URLSearchParams {
  const searchParams = new URLSearchParams();

  searchParams.set("format", params.format);

  for (const eventId of params.event_ids ?? []) {
    if (eventId.trim()) {
      searchParams.append("event_ids", eventId.trim());
    }
  }

  appendText(searchParams, "date_from", params.date_from);
  appendText(searchParams, "date_to", params.date_to);
  appendText(searchParams, "state", params.state);
  appendBoolean(searchParams, "is_checked_in", params.is_checked_in);
  appendText(searchParams, "email", params.email);
  appendText(searchParams, "first_name", params.first_name);
  appendText(searchParams, "last_name", params.last_name);
  appendBoolean(searchParams, "is_batch", params.is_batch);
  appendText(searchParams, "payment_status", params.payment_status);
  appendText(searchParams, "paid_from", params.paid_from);
  appendText(searchParams, "paid_to", params.paid_to);
  appendNumber(searchParams, "amount_min", params.amount_min);
  appendNumber(searchParams, "amount_max", params.amount_max);

  for (const customFieldFilter of params.custom_field ?? []) {
    const trimmed = customFieldFilter.trim();
    if (trimmed) {
      searchParams.append("custom_field", trimmed);
    }
  }

  searchParams.set("sort_by", params.sort_by?.trim() || "registered_at");
  searchParams.set("sort_order", params.sort_order ?? "desc");

  return searchParams;
}

function appendText(
  searchParams: URLSearchParams,
  key: string,
  value: string | undefined,
) {
  if (!value?.trim()) {
    return;
  }

  searchParams.set(key, value.trim());
}

function appendBoolean(
  searchParams: URLSearchParams,
  key: string,
  value: boolean | undefined,
) {
  if (value === undefined) {
    return;
  }

  searchParams.set(key, value ? "true" : "false");
}

function appendNumber(
  searchParams: URLSearchParams,
  key: string,
  value: number | undefined,
) {
  if (value === undefined || Number.isNaN(value)) {
    return;
  }

  searchParams.set(key, String(value));
}

function extractFilename(contentDispositionHeader: unknown): string | null {
  if (typeof contentDispositionHeader !== "string") {
    return null;
  }

  const match = contentDispositionHeader.match(/filename="(?<filename>[^"]+)"/i);
  return match?.groups?.filename ?? null;
}

function defaultFilenameForFormat(format: AdminAnalyticsDownloadParams["format"]): string {
  return format === "pdf" ? "analytics-download.pdf" : "analytics-download.csv";
}
