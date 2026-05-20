import { NavLink, Outlet } from "react-router-dom";

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
  return (
    <div className="dashboard-shell">
      <aside className="dashboard-sidebar">
        <NavLink to="/admin" end className="brand-link brand-link--sidebar">
          Admin Workspace
        </NavLink>
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
      </aside>
      <main className="dashboard-main">
        <Outlet />
      </main>
    </div>
  );
}
