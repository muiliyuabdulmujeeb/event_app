import { Navigate, useRoutes } from "react-router-dom";

import { AdminLayout } from "../layouts/AdminLayout";
import { AuthLayout } from "../layouts/AuthLayout";
import { PublicLayout } from "../layouts/PublicLayout";
import { StaffLayout } from "../layouts/StaffLayout";
import { AdminRoute } from "./AdminRoute";
import { ProtectedRoute } from "./ProtectedRoute";
import { AdminLoginPage } from "../pages/AdminLoginPage";
import { BatchRegistrationPage } from "../pages/BatchRegistrationPage";
import { EventDetailPage } from "../pages/EventDetailPage";
import { EventListPage } from "../pages/EventListPage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { PaymentStatusPage } from "../pages/PaymentStatusPage";
import { PlaceholderPage } from "../pages/PlaceholderPage";
import { RegistrationLookupPage } from "../pages/RegistrationLookupPage";
import { SingleRegistrationPage } from "../pages/SingleRegistrationPage";
import { StaffDashboardPage } from "../pages/StaffDashboardPage";
import { StaffLoginPage } from "../pages/StaffLoginPage";
import { StaffNotificationsPage } from "../pages/StaffNotificationsPage";
import { StaffRegistrationsPage } from "../pages/StaffRegistrationsPage";

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
          element: <SingleRegistrationPage />,
        },
        {
          path: "/events/:eventId/register/batch",
          element: <BatchRegistrationPage />,
        },
        {
          path: "/registrations/lookup",
          element: <RegistrationLookupPage />,
        },
        {
          path: "/payment/success",
          element: <PaymentStatusPage variant="success" />,
        },
        {
          path: "/payment/failure",
          element: <PaymentStatusPage variant="failure" />,
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
              element: <StaffDashboardPage />,
            },
            {
              path: "/staff/registrations",
              element: <StaffRegistrationsPage />,
            },
            {
              path: "/staff/notifications",
              element: <StaffNotificationsPage />,
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
