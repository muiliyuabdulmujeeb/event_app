import { NavLink, Outlet } from "react-router-dom";

const staffLinks = [
  { to: "/staff", label: "Dashboard", end: true },
  { to: "/staff/registrations", label: "Registrations" },
  { to: "/staff/notifications", label: "Notifications" },
];

export function StaffLayout() {
  return (
    <div className="dashboard-shell">
      <aside className="dashboard-sidebar">
        <NavLink to="/staff" end className="brand-link brand-link--sidebar">
          Staff Workspace
        </NavLink>
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
      </aside>
      <main className="dashboard-main">
        <Outlet />
      </main>
    </div>
  );
}
