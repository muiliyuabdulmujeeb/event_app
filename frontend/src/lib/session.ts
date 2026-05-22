import { useSyncExternalStore } from "react";
import { z } from "zod";

export const AUTH_REQUIRED_EVENT = "event-manager:auth-required";

const SESSION_STORAGE_KEY = "event-manager.auth-session";
const SESSION_CHANGED_EVENT = "event-manager:session-changed";

const sessionSchema = z.object({
  accessToken: z.string().min(1),
  refreshToken: z.string().min(1),
  role: z.enum(["admin", "staff"]),
});

export type AuthSession = z.infer<typeof sessionSchema>;
export type AuthRole = AuthSession["role"];

export function getAuthSession(): AuthSession | null {
  if (typeof window === "undefined") {
    return null;
  }

  const rawValue = window.localStorage.getItem(SESSION_STORAGE_KEY);
  if (!rawValue) {
    return null;
  }

  try {
    const parsed = JSON.parse(rawValue);
    const result = sessionSchema.safeParse(parsed);
    if (result.success) {
      return result.data;
    }

    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  } catch {
    window.localStorage.removeItem(SESSION_STORAGE_KEY);
    return null;
  }
}

export function setAuthSession(session: AuthSession): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
  emitSessionChanged();
}

export function clearAuthSession(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.localStorage.removeItem(SESSION_STORAGE_KEY);
  emitSessionChanged();
}

export function getAccessToken(): string | null {
  return getAuthSession()?.accessToken ?? null;
}

export function getRefreshToken(): string | null {
  return getAuthSession()?.refreshToken ?? null;
}

export function getAuthRole(): AuthRole | null {
  return getAuthSession()?.role ?? null;
}

export function updateAccessToken(accessToken: string): void {
  const session = getAuthSession();
  if (!session || typeof window === "undefined") {
    return;
  }

  window.localStorage.setItem(
    SESSION_STORAGE_KEY,
    JSON.stringify({
      ...session,
      accessToken,
    }),
  );
  emitSessionChanged();
}

export function useAuthSession(): AuthSession | null {
  return useSyncExternalStore(subscribeToSessionChanges, getAuthSession, () => null);
}

export function notifyAuthRequired(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(new Event(AUTH_REQUIRED_EVENT));
}

function subscribeToSessionChanges(onStoreChange: () => void): () => void {
  if (typeof window === "undefined") {
    return () => undefined;
  }

  const handleStorage = (event: StorageEvent) => {
    if (event.key === SESSION_STORAGE_KEY) {
      onStoreChange();
    }
  };

  const handleSessionChanged = () => onStoreChange();

  window.addEventListener("storage", handleStorage);
  window.addEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);

  return () => {
    window.removeEventListener("storage", handleStorage);
    window.removeEventListener(SESSION_CHANGED_EVENT, handleSessionChanged);
  };
}

function emitSessionChanged(): void {
  if (typeof window === "undefined") {
    return;
  }

  window.dispatchEvent(new Event(SESSION_CHANGED_EVENT));
}
