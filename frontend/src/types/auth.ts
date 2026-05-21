import { z } from "zod";

export const authRoleSchema = z.enum(["admin", "staff"]);

export const loginRequestSchema = z.object({
  email: z
    .string()
    .trim()
    .min(1, "Email is required.")
    .email("Enter a valid email address."),
  password: z.string().min(1, "Password is required."),
});

export const loginResponseSchema = z.object({
  access_token: z.string().min(1),
  refresh_token: z.string().min(1),
  token_type: z.literal("bearer"),
  access_token_expires_in: z.number().int().positive(),
  refresh_token_expires_in: z.number().int().positive(),
  role: authRoleSchema,
});

export const refreshAccessTokenRequestSchema = z.object({
  refresh_token: z.string().min(1),
});

export const refreshAccessTokenResponseSchema = z.object({
  access_token: z.string().min(1),
  token_type: z.literal("bearer"),
  access_token_expires_in: z.number().int().positive(),
});

export type AuthRole = z.infer<typeof authRoleSchema>;
export type LoginRequest = z.infer<typeof loginRequestSchema>;
export type LoginResponse = z.infer<typeof loginResponseSchema>;
export type RefreshAccessTokenRequest = z.infer<typeof refreshAccessTokenRequestSchema>;
export type RefreshAccessTokenResponse = z.infer<typeof refreshAccessTokenResponseSchema>;
