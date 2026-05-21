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

export function formatDate(value: string | Date | null | undefined, fallback = "--"): string {
  const parsed = parseUtcTimestamp(value);
  return parsed ? dateFormatter.format(parsed) : fallback;
}

export function formatDateTime(value: string | Date | null | undefined, fallback = "--"): string {
  const parsed = parseUtcTimestamp(value);
  return parsed ? dateTimeFormatter.format(parsed) : fallback;
}

export function toDateTimeLocalInputValue(value: string | Date | null | undefined): string {
  const parsed = parseUtcTimestamp(value);
  if (!parsed) {
    return "";
  }

  return `${parsed.getFullYear()}-${pad(parsed.getMonth() + 1)}-${pad(parsed.getDate())}T${pad(parsed.getHours())}:${pad(parsed.getMinutes())}`;
}

export function fromDateTimeLocalInputValue(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }

  const parsed = new Date(trimmed);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }

  return parsed.toISOString();
}

function pad(value: number): string {
  return value.toString().padStart(2, "0");
}
