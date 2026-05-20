import axios from "axios";
import { z } from "zod";

const validationItemSchema = z.object({
  loc: z.array(z.union([z.string(), z.number()])),
  msg: z.string(),
});

const errorPayloadSchema = z.object({
  detail: z.union([z.string(), z.array(validationItemSchema)]).optional(),
});

export type ApiErrorCode =
  | "unauthorized"
  | "forbidden"
  | "notFound"
  | "conflict"
  | "validation"
  | "network"
  | "invalidPayload"
  | "unknown";

export class ApiError extends Error {
  readonly code: ApiErrorCode;
  readonly status?: number;
  readonly fieldErrors?: Record<string, string[]>;

  constructor(
    message: string,
    options: {
      code: ApiErrorCode;
      status?: number;
      fieldErrors?: Record<string, string[]>;
    },
  ) {
    super(message);
    this.name = "ApiError";
    this.code = options.code;
    this.status = options.status;
    this.fieldErrors = options.fieldErrors;
  }
}

export function createInvalidPayloadError(context: string): ApiError {
  return new ApiError(
    `Received an unexpected response while loading ${context}. Please refresh and try again.`,
    { code: "invalidPayload" },
  );
}

export function normalizeApiError(error: unknown): ApiError {
  if (error instanceof ApiError) {
    return error;
  }

  if (axios.isAxiosError(error)) {
    const status = error.response?.status;
    if (!status) {
      return new ApiError(
        "The request could not be completed. Check your connection and try again.",
        { code: "network" },
      );
    }

    const parsedPayload = errorPayloadSchema.safeParse(error.response?.data);
    const detail = parsedPayload.success ? parsedPayload.data.detail : undefined;

    if (Array.isArray(detail)) {
      return new ApiError("Please correct the highlighted fields and try again.", {
        code: "validation",
        status,
        fieldErrors: groupFieldErrors(detail),
      });
    }

    const detailMessage = typeof detail === "string" && detail.trim() ? detail.trim() : undefined;
    const fallbackMessage = statusToFallbackMessage(status);

    return new ApiError(detailMessage ?? fallbackMessage, {
      code: statusToErrorCode(status),
      status,
    });
  }

  if (error instanceof Error) {
    return new ApiError(error.message || "Something went wrong. Please try again.", {
      code: "unknown",
    });
  }

  return new ApiError("Something went wrong. Please try again.", { code: "unknown" });
}

function statusToErrorCode(status: number): ApiErrorCode {
  if (status === 401) {
    return "unauthorized";
  }
  if (status === 403) {
    return "forbidden";
  }
  if (status === 404) {
    return "notFound";
  }
  if (status === 409) {
    return "conflict";
  }
  if (status === 422 || status === 400) {
    return "validation";
  }
  return "unknown";
}

function statusToFallbackMessage(status: number): string {
  if (status === 401) {
    return "Your session is no longer valid. Please sign in again.";
  }
  if (status === 403) {
    return "You do not have permission to perform this action.";
  }
  if (status === 404) {
    return "The requested resource could not be found.";
  }
  if (status === 409) {
    return "This action could not be completed because the record changed or is no longer eligible.";
  }
  if (status === 422 || status === 400) {
    return "Please review the submitted information and try again.";
  }
  if (status >= 500) {
    return "The server could not complete the request. Please try again shortly.";
  }
  return "Something went wrong. Please try again.";
}

function groupFieldErrors(
  details: Array<z.infer<typeof validationItemSchema>>,
): Record<string, string[]> {
  return details.reduce<Record<string, string[]>>((accumulator, detail) => {
    const field = detail.loc
      .filter((part) => typeof part === "string")
      .join(".")
      .replace(/^body\./, "")
      .replace(/^query\./, "");

    const key = field || "form";
    if (!accumulator[key]) {
      accumulator[key] = [];
    }
    accumulator[key].push(detail.msg);
    return accumulator;
  }, {});
}
