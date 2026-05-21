import { http } from "./http";
import { parseApiResponse } from "../lib/apiParsers";
import {
  LoginRequest,
  LoginResponse,
  RefreshAccessTokenRequest,
  RefreshAccessTokenResponse,
  loginResponseSchema,
  refreshAccessTokenResponseSchema,
} from "../types/auth";

export async function login(
  payload: LoginRequest,
  signal?: AbortSignal,
): Promise<LoginResponse> {
  const response = await http.post("/auth/login", payload, { signal });
  return parseApiResponse(loginResponseSchema, response.data, "the login response");
}

export async function refreshAccessToken(
  payload: RefreshAccessTokenRequest,
): Promise<RefreshAccessTokenResponse> {
  const response = await http.post("/auth/refresh", payload, {
    skipAuthRefresh: true,
  });
  return parseApiResponse(
    refreshAccessTokenResponseSchema,
    response.data,
    "the refresh-token response",
  );
}
