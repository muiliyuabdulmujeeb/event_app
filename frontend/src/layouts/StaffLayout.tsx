import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { queryClient } from "../lib/queryClient";
import { clearAuthSession, useAuthSession } from "../lib/session";

const staffLinks = [
  { to: "/staff", label: "Dashboard", end: true },
  { to: "/staff/registrations", label: "Registrations" },
  { to: "/staff/notifications", label: "Notifications" },
];

export function StaffLayout() {
  const navigate = useNavigate();
  const session = useAuthSession();

  function handleLogout() {
    clearAuthSession();
    queryClient.clear();
    navigate("/staff/login", { replace: true });
  }

  return (
    <div className="dashboard-shell">
      <aside className="dashboard-sidebar">
        <NavLink to="/staff" end className="brand-link brand-link--sidebar">
          Staff Workspace
        </NavLink>
        <p className="sidebar-meta">
          Signed in as <strong>{session?.role ?? "staff"}</strong>
        </p>
        <nav aria-label="Staff navigation" className="dashboard-nav">
          {staffLinks.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              end={link.end}
              className={({ isActive }) => (isActive ? "nav-link nav-link--active" : "nav-link")}
            >
              {link.label}
            </NavLink>
          ))}
        </nav>
        <div className="sidebar-footer">
          <button type="button" className="button-link button-link--secondary" onClick={handleLogout}>
            Sign out
          </button>
        </div>
      </aside>
      <main className="dashboard-main">
        <Outlet />
      </main>
    </div>
  );
}
