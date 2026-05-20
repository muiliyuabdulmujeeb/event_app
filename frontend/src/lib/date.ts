const dateFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
});

const dateTimeFormatter = new Intl.DateTimeFormat(undefined, {
  dateStyle: "medium",
  timeStyle: "short",
});

export function parseUtcTimestamp(value: string | Date | null | undefined): Date | null {
  if (!value) {
    return null;
  }
  const date = value instanceof Date ? value : new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

export function formatDate(value: string | Date | null | undefined, fallback = "—"): string {
  const parsed = parseUtcTimestamp(value);
  return parsed ? dateFormatter.format(parsed) : fallback;
}

export function formatDateTime(value: string | Date | null | undefined, fallback = "—"): string {
  const parsed = parseUtcTimestamp(value);
  return parsed ? dateTimeFormatter.format(parsed) : fallback;
}
