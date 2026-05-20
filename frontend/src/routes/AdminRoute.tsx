import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuthSession } from "../lib/session";

export function AdminRoute() {
  const session = useAuthSession();
  const location = useLocation();

  if (!session) {
    return <Navigate to="/admin/login" replace state={{ from: location }} />;
  }

  if (session.role !== "admin") {
    return <Navigate to="/staff" replace />;
  }

  return <Outlet />;
}
