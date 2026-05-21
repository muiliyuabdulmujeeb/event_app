import { NavLink, Outlet, useNavigate } from "react-router-dom";

import { queryClient } from "../lib/queryClient";
import { clearAuthSession, useAuthSession } from "../lib/session";

const adminLinks = [
  { to: "/admin", label: "Dashboard", end: true },
  { to: "/admin/events", label: "Events" },
  { to: "/admin/staff", label: "Staff" },
  { to: "/admin/registrations", label: "Registrations" },
  { to: "/admin/refunds", label: "Refunds" },
  { to: "/admin/notifications", label: "Notifications" },
  { to: "/admin/analytics", label: "Analytics" },
];

export function AdminLayout() {
  const navigate = useNavigate();
  const session = useAuthSession();

  function handleLogout() {
    clearAuthSession();
    queryClient.clear();
    navigate("/admin/login", { replace: true });
  }

  return (
    <div className="dashboard-shell">
      <aside className="dashboard-sidebar">
        <NavLink to="/admin" end className="brand-link brand-link--sidebar">
          Admin Workspace
        </NavLink>
        <p className="sidebar-meta">
          Signed in as <strong>{session?.role ?? "admin"}</strong>
        </p>
        <nav aria-label="Admin navigation" className="dashboard-nav">
          {adminLinks.map((link) => (
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
