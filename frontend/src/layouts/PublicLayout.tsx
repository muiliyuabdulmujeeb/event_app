import { NavLink, Outlet } from "react-router-dom";

import { PageContainer } from "../components/PageContainer";

const publicLinks = [
  { to: "/events", label: "Events" },
  { to: "/registrations/lookup", label: "Lookup" },
  { to: "/staff/login", label: "Staff Login" },
  { to: "/admin/login", label: "Admin Login" },
];

export function PublicLayout() {
  return (
    <div className="site-shell">
      <header className="site-header">
        <div className="site-header__inner">
          <NavLink to="/events" className="brand-link">
            Event Management App
          </NavLink>
          <nav aria-label="Primary" className="site-nav">
            {publicLinks.map((link) => (
              <NavLink
                key={link.to}
                to={link.to}
                className={({ isActive }) => (isActive ? "nav-link nav-link--active" : "nav-link")}
              >
                {link.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <PageContainer>
        <Outlet />
      </PageContainer>
    </div>
  );
}
