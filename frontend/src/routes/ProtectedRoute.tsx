import { Navigate, Outlet, useLocation } from "react-router-dom";

import { useAuthSession } from "../lib/session";

export function ProtectedRoute() {
  const session = useAuthSession();
  const location = useLocation();

  if (!session) {
    return <Navigate to="/staff/login" replace state={{ from: location }} />;
  }

  return <Outlet />;
}
