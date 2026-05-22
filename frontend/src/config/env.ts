import { z } from "zod";

const envSchema = z.object({
  VITE_API_BASE_URL: z
    .string({
      required_error: "VITE_API_BASE_URL is required.",
    })
    .trim()
    .min(1, "VITE_API_BASE_URL is required.")
    .url("VITE_API_BASE_URL must be a full URL such as http://localhost:8000."),
});

export type AppEnv = z.infer<typeof envSchema>;

export type AppEnvValidationResult =
  | { success: true; env: AppEnv }
  | { success: false; message: string; issues: string[] };

let cachedEnv: AppEnv | null = null;

export function validateAppEnv(source: unknown = import.meta.env): AppEnvValidationResult {
  const parsed = envSchema.safeParse(source);

  if (parsed.success) {
    return {
      success: true,
      env: parsed.data,
    };
  }

  return {
    success: false,
    message:
      "Frontend configuration is incomplete. Set VITE_API_BASE_URL in frontend/.env and restart the app.",
    issues: parsed.error.issues.map((issue) => issue.message),
  };
}

export function getAppEnv(): AppEnv {
  if (cachedEnv) {
    return cachedEnv;
  }

  const validation = validateAppEnv();
  if (!validation.success) {
    throw new Error(validation.message);
  }

  cachedEnv = validation.env;
  return cachedEnv;
}
