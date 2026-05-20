import { z } from "zod";

const envSchema = z.object({
  VITE_API_BASE_URL: z.string().trim().min(1).url(),
});

export type AppEnv = z.infer<typeof envSchema>;

export const env: AppEnv = envSchema.parse(import.meta.env);
