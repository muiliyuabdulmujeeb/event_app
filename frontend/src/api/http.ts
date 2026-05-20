import axios from "axios";

import { env } from "../config/env";
import { normalizeApiError } from "../lib/apiError";
import { clearAuthSession, getAccessToken, notifyAuthRequired } from "../lib/session";

export const http = axios.create({
  baseURL: env.VITE_API_BASE_URL,
  headers: {
    Accept: "application/json",
  },
  timeout: 15_000,
});

http.interceptors.request.use((config) => {
  const accessToken = getAccessToken();
  if (accessToken) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    const normalizedError = normalizeApiError(error);
    if (normalizedError.status === 401) {
      clearAuthSession();
      notifyAuthRequired();
    }
    return Promise.reject(normalizedError);
  },
);
