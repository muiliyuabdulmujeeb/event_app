import { zodResolver } from "@hookform/resolvers/zod";
import { useMutation } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Navigate, useLocation, useNavigate } from "react-router-dom";

import { login } from "../../api/auth";
import { ApiError } from "../../lib/apiError";
import { setAuthSession, useAuthSession } from "../../lib/session";
import {
  AuthRole,
  LoginRequest,
  loginRequestSchema,
} from "../../types/auth";
import { PageHeader } from "../PageHeader";

type LoginFormProps = {
  mode: "staff" | "admin";
};

type LoginLocationState = {
  from?: {
    pathname?: string;
  };
};

const copyByMode = {
  staff: {
    eyebrow: "Staff Access",
    title: "Staff sign in",
    description:
      "Use your staff or admin credentials to access registrations, check-in operations, and internal workflows.",
    submitLabel: "Sign in to staff workspace",
  },
  admin: {
    eyebrow: "Admin Access",
    title: "Admin sign in",
    description:
      "Use your admin credentials to manage events, staff access, refunds, notifications, and analytics.",
    submitLabel: "Sign in to admin workspace",
  },
} as const;

export function LoginForm({ mode }: LoginFormProps) {
  const session = useAuthSession();
  const navigate = useNavigate();
  const location = useLocation();
  const copy = copyByMode[mode];

  const form = useForm<LoginRequest>({
    resolver: zodResolver(loginRequestSchema),
    defaultValues: {
      email: "",
      password: "",
    },
    mode: "onBlur",
  });

  const mutation = useMutation({
    mutationFn: login,
    onSuccess: (response) => {
      setAuthSession({
        accessToken: response.access_token,
        refreshToken: response.refresh_token,
        role: response.role,
      });
      navigate(resolvePostLoginPath(response.role, location.state), { replace: true });
    },
    onError: (error) => {
      const apiError =
        error instanceof ApiError
          ? error
          : new ApiError("Unable to sign in right now. Please try again.", {
              code: "unknown",
            });

      applyFieldErrors(form.setError, apiError.fieldErrors);
      if (!apiError.fieldErrors || Object.keys(apiError.fieldErrors).length === 0) {
        form.setError("root", {
          message: apiError.message,
        });
      }
    },
  });

  if (session) {
    return (
      <Navigate
        to={resolvePostLoginPath(session.role, location.state)}
        replace
      />
    );
  }

  return (
    <section className="panel">
      <PageHeader
        eyebrow={copy.eyebrow}
        title={copy.title}
        description={copy.description}
      />
      <form
        className="auth-form"
        noValidate
        onSubmit={form.handleSubmit((values) => mutation.mutate(values))}
      >
        <div className="form-field">
          <label className="form-label" htmlFor={`${mode}-email`}>
            Email address
          </label>
          <input
            id={`${mode}-email`}
            type="email"
            autoComplete="username"
            className="form-input"
            aria-invalid={form.formState.errors.email ? "true" : "false"}
            aria-describedby={form.formState.errors.email ? `${mode}-email-error` : undefined}
            {...form.register("email")}
          />
          {form.formState.errors.email ? (
            <p id={`${mode}-email-error`} className="form-error" role="alert">
              {form.formState.errors.email.message}
            </p>
          ) : null}
        </div>

        <div className="form-field">
          <label className="form-label" htmlFor={`${mode}-password`}>
            Password
          </label>
          <input
            id={`${mode}-password`}
            type="password"
            autoComplete="current-password"
            className="form-input"
            aria-invalid={form.formState.errors.password ? "true" : "false"}
            aria-describedby={
              form.formState.errors.password ? `${mode}-password-error` : undefined
            }
            {...form.register("password")}
          />
          {form.formState.errors.password ? (
            <p id={`${mode}-password-error`} className="form-error" role="alert">
              {form.formState.errors.password.message}
            </p>
          ) : null}
        </div>

        {form.formState.errors.root ? (
          <div className="form-alert" role="alert">
            {form.formState.errors.root.message}
          </div>
        ) : null}

        <div className="panel__actions">
          <button
            type="submit"
            className="button-link button-link--primary"
            disabled={mutation.isPending}
          >
            {mutation.isPending ? "Signing in…" : copy.submitLabel}
          </button>
        </div>
      </form>
    </section>
  );
}

function resolvePostLoginPath(role: AuthRole, state: unknown): string {
  const fromPath = extractRedirectPath(state);
  if (fromPath?.startsWith("/admin")) {
    return role === "admin" ? fromPath : "/staff";
  }
  if (fromPath?.startsWith("/staff")) {
    return fromPath;
  }
  return role === "admin" ? "/admin" : "/staff";
}

function extractRedirectPath(state: unknown): string | null {
  const typedState = state as LoginLocationState | null | undefined;
  const pathname = typedState?.from?.pathname;
  return typeof pathname === "string" && pathname.trim() ? pathname : null;
}

function applyFieldErrors(
  setError: ReturnType<typeof useForm<LoginRequest>>["setError"],
  fieldErrors?: Record<string, string[]>,
) {
  if (!fieldErrors) {
    return;
  }

  for (const [field, messages] of Object.entries(fieldErrors)) {
    const message = messages[0];
    if (!message) {
      continue;
    }

    if (field === "email" || field === "password") {
      setError(field, { message });
      continue;
    }

    setError("root", { message });
  }
}
