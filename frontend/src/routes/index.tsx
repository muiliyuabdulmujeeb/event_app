import { Navigate, useRoutes } from "react-router-dom";

import { AdminLayout } from "../layouts/AdminLayout";
import { AuthLayout } from "../layouts/AuthLayout";
import { PublicLayout } from "../layouts/PublicLayout";
import { StaffLayout } from "../layouts/StaffLayout";
import { AdminRoute } from "./AdminRoute";
import { ProtectedRoute } from "./ProtectedRoute";
import { AdminLoginPage } from "../pages/AdminLoginPage";
import { AdminCreateEventPage } from "../pages/AdminCreateEventPage";
import { AdminDashboardPage } from "../pages/AdminDashboardPage";
import { AdminEditEventPage } from "../pages/AdminEditEventPage";
import { AdminAnalyticsPage } from "../pages/AdminAnalyticsPage";
import { AdminEventsPage } from "../pages/AdminEventsPage";
import { AdminNotificationsPage } from "../pages/AdminNotificationsPage";
import { AdminRegistrationsPage } from "../pages/AdminRegistrationsPage";
import { AdminRefundsPage } from "../pages/AdminRefundsPage";
import { AdminStaffDetailPage } from "../pages/AdminStaffDetailPage";
import { AdminStaffPage } from "../pages/AdminStaffPage";
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
              element: <AdminDashboardPage />,
            },
            {
              path: "/admin/events",
              element: <AdminEventsPage />,
            },
            {
              path: "/admin/events/new",
              element: <AdminCreateEventPage />,
            },
            {
              path: "/admin/events/:eventId/edit",
              element: <AdminEditEventPage />,
            },
            {
              path: "/admin/staff",
              element: <AdminStaffPage />,
            },
            {
              path: "/admin/staff/:staffId",
              element: <AdminStaffDetailPage />,
            },
            {
              path: "/admin/registrations",
              element: <AdminRegistrationsPage />,
            },
            {
              path: "/admin/refunds",
              element: <AdminRefundsPage />,
            },
            {
              path: "/admin/notifications",
              element: <AdminNotificationsPage />,
            },
            {
              path: "/admin/analytics",
              element: <AdminAnalyticsPage />,
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
