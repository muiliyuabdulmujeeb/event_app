import axios, {
  AxiosHeaders,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
} from "axios";

import { env } from "../config/env";
import { normalizeApiError } from "../lib/apiError";
import {
  clearAuthSession,
  getAccessToken,
  getRefreshToken,
  notifyAuthRequired,
  updateAccessToken,
} from "../lib/session";
import { parseApiResponse } from "../lib/apiParsers";
import { refreshAccessTokenResponseSchema } from "../types/auth";

type ExtendedAxiosRequestConfig = InternalAxiosRequestConfig & {
  _retry?: boolean;
  skipAuthRefresh?: boolean;
};

export const http = axios.create({
  baseURL: env.VITE_API_BASE_URL,
  headers: {
    Accept: "application/json",
  },
  timeout: 15_000,
});

let refreshPromise: Promise<string> | null = null;

http.interceptors.request.use((config: ExtendedAxiosRequestConfig) => {
  const accessToken = getAccessToken();
  if (accessToken) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  async (error: unknown) => {
    if (!axios.isAxiosError(error)) {
      return Promise.reject(normalizeApiError(error));
    }

    const originalRequest = error.config as ExtendedAxiosRequestConfig | undefined;
    const status = error.response?.status;

    if (
      status !== 401 ||
      !originalRequest ||
      originalRequest.skipAuthRefresh ||
      originalRequest._retry
    ) {
      const normalizedError = normalizeApiError(error);
      if (status === 401) {
        clearAuthSession();
        notifyAuthRequired();
      }
      return Promise.reject(normalizedError);
    }

    const refreshToken = getRefreshToken();
    if (!refreshToken) {
      clearAuthSession();
      notifyAuthRequired();
      return Promise.reject(normalizeApiError(error));
    }

    originalRequest._retry = true;

    try {
      const nextAccessToken = await refreshAccessTokenWithSingleFlight(refreshToken);
      setAuthorizationHeader(originalRequest, nextAccessToken);
      return http(originalRequest);
    } catch (refreshError) {
      clearAuthSession();
      notifyAuthRequired();
      return Promise.reject(normalizeApiError(refreshError));
    }
  },
);

async function refreshAccessTokenWithSingleFlight(refreshToken: string): Promise<string> {
  if (!refreshPromise) {
    refreshPromise = requestAccessTokenRefresh(refreshToken).finally(() => {
      refreshPromise = null;
    });
  }

  return refreshPromise;
}

async function requestAccessTokenRefresh(refreshToken: string): Promise<string> {
  const response = await axios.post(
    `${env.VITE_API_BASE_URL}/auth/refresh`,
    {
      refresh_token: refreshToken,
    },
    {
      headers: {
        Accept: "application/json",
      },
      timeout: 15_000,
    },
  );

  const parsed = parseApiResponse(
    refreshAccessTokenResponseSchema,
    response.data,
    "the refreshed access token",
  );
  updateAccessToken(parsed.access_token);
  return parsed.access_token;
}

function setAuthorizationHeader(
  config: AxiosRequestConfig,
  accessToken: string,
) {
  if (!config.headers) {
    config.headers = new AxiosHeaders();
  }

  if (config.headers instanceof AxiosHeaders) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
    return;
  }

  config.headers = {
    ...config.headers,
    Authorization: `Bearer ${accessToken}`,
  };
}
