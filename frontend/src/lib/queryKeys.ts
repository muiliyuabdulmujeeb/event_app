export const queryKeys = {
  auth: {
    session: ["auth", "session"] as const,
  },
  publicEvents: {
    all: ["public-events"] as const,
    list: (params: { search?: string; isFree?: boolean | null }) =>
      ["public-events", "list", params] as const,
    detail: (eventId: string) => ["public-events", "detail", eventId] as const,
  },
  registrations: {
    lookup: (regId: string) => ["registrations", "lookup", regId] as const,
    eventForm: (eventId: string) => ["registrations", "event-form", eventId] as const,
  },
  staff: {
    notifications: ["staff", "notifications"] as const,
    registrations: (params: { regId?: string; email?: string }) =>
      ["staff", "registrations", params] as const,
  },
  adminEvents: {
    all: ["admin-events"] as const,
    detail: (eventId: string) => ["admin-events", "detail", eventId] as const,
  },
  adminStaff: {
    all: ["admin-staff"] as const,
    detail: (staffId: string) => ["admin-staff", "detail", staffId] as const,
  },
  refunds: {
    list: (params: { status?: string; eventId?: string; regId?: string }) =>
      ["refunds", "list", params] as const,
  },
  analytics: {
    summary: (params: { eventIds?: string[]; dateFrom?: string; dateTo?: string }) =>
      ["analytics", "summary", params] as const,
    registrations: (params: Record<string, unknown>) =>
      ["analytics", "registrations", params] as const,
  },
} as const;
