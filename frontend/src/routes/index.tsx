import { Navigate, useRoutes } from "react-router-dom";

import { AdminLayout } from "../layouts/AdminLayout";
import { AuthLayout } from "../layouts/AuthLayout";
import { PublicLayout } from "../layouts/PublicLayout";
import { StaffLayout } from "../layouts/StaffLayout";
import { AdminRoute } from "./AdminRoute";
import { ProtectedRoute } from "./ProtectedRoute";
import { AdminLoginPage } from "../pages/AdminLoginPage";
import { EventDetailPage } from "../pages/EventDetailPage";
import { EventListPage } from "../pages/EventListPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { StaffLoginPage } from "../pages/StaffLoginPage";

export function AppRoutes() {
  return useRoutes([
    {
      path: "/",
      element: <Navigate to="/events" replace />,
    },
    {
      element: <PublicLayout />,
      children: [
        {
          path: "/events",
          element: <EventListPage />,
        },
        {
          path: "/events/:eventId",
          element: <EventDetailPage />,
        },
        {
          path: "/events/:eventId/register",
          element: (
            <PlaceholderPage
              eyebrow="Public"
              title="Single registration"
              description="The single-attendee registration workflow will be connected to the backend in later phases."
            />
          ),
        },
        {
          path: "/events/:eventId/register/batch",
          element: (
            <PlaceholderPage
              eyebrow="Public"
              title="Batch registration"
              description="The batch registration workflow will be connected to the backend in later phases."
            />
          ),
        },
        {
          path: "/registrations/lookup",
          element: (
            <PlaceholderPage
              eyebrow="Public"
              title="Registration lookup"
              description="Lookup by registration ID and user notification handling will be implemented in a later phase."
            />
          ),
        },
        {
          path: "/payment/success",
          element: (
            <PlaceholderPage
              eyebrow="Payments"
              title="Payment success"
              description="This page will later read gateway callback query parameters and confirm successful payment outcomes."
            />
          ),
        },
        {
          path: "/payment/failure",
          element: (
            <PlaceholderPage
              eyebrow="Payments"
              title="Payment failure"
              description="This page will later read gateway callback query parameters and display payment failure outcomes."
            />
          ),
        },
      ],
    },
    {
      element: <AuthLayout />,
      children: [
        {
          path: "/staff/login",
          element: <StaffLoginPage />,
        },
        {
          path: "/admin/login",
          element: <AdminLoginPage />,
        },
      ],
    },
    {
      element: <ProtectedRoute />,
      children: [
        {
          element: <StaffLayout />,
          children: [
            {
              path: "/staff",
              element: (
                <PlaceholderPage
                  eyebrow="Staff"
                  title="Staff dashboard"
                  description="Staff dashboard composition will be built after the shared auth and API layers are in place."
                />
              ),
            },
            {
              path: "/staff/registrations",
              element: (
                <PlaceholderPage
                  eyebrow="Staff"
                  title="Registration operations"
                  description="Registration search, check-in, and reverse check-in will be implemented in a later phase."
                />
              ),
            },
            {
              path: "/staff/notifications",
              element: (
                <PlaceholderPage
                  eyebrow="Staff"
                  title="Staff notifications"
                  description="Unread staff notifications will be surfaced here once the staff workspace is connected."
                />
              ),
            },
          ],
        },
      ],
    },
    {
      element: <AdminRoute />,
      children: [
        {
          element: <AdminLayout />,
          children: [
            {
              path: "/admin",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Admin dashboard"
                  description="The dashboard will be composed from existing backend endpoints once the auth and API layers are connected."
                />
              ),
            },
            {
              path: "/admin/events",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Events"
                  description="Event listing, creation, and editing will be implemented in later frontend phases."
                />
              ),
            },
            {
              path: "/admin/events/new",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Create event"
                  description="The event creation form will be implemented once the shared form and API layers are in use."
                />
              ),
            },
            {
              path: "/admin/events/:eventId/edit",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Edit event"
                  description="Event editing and state update flows will be implemented in later phases."
                />
              ),
            },
            {
              path: "/admin/staff",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Staff management"
                  description="Staff account management, access modes, and selected-event assignment will be implemented later."
                />
              ),
            },
            {
              path: "/admin/staff/:staffId",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Staff account details"
                  description="This route is reserved for detailed staff access management."
                />
              ),
            },
            {
              path: "/admin/registrations",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Registration table"
                  description="This page will later use the analytics registration endpoint as the source of truth."
                />
              ),
            },
            {
              path: "/admin/refunds",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Refund requests"
                  description="Refund request review and processing will be implemented in a later phase."
                />
              ),
            },
            {
              path: "/admin/notifications",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Notification dispatch"
                  description="Admin-triggered notifications will be added once the shared admin API layer is connected."
                />
              ),
            },
            {
              path: "/admin/analytics",
              element: (
                <PlaceholderPage
                  eyebrow="Admin"
                  title="Analytics"
                  description="Analytics and export flows will be implemented in a later frontend phase."
                />
              ),
            },
          ],
        },
      ],
    },
    {
      path: "*",
      element: <NotFoundPage />,
    },
  ]);
}
