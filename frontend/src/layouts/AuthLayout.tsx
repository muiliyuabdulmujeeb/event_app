import { NavLink, Outlet } from "react-router-dom";

import { PageContainer } from "../components/PageContainer";

export function AuthLayout() {
  return (
    <div className="auth-shell">
      <PageContainer narrow>
        <section className="panel">
          <nav className="segment-nav" aria-label="Auth sections">
            <NavLink
              to="/staff/login"
              className={({ isActive }) =>
                isActive ? "segment-nav__link segment-nav__link--active" : "segment-nav__link"
              }
            >
              Staff
            </NavLink>
            <NavLink
              to="/admin/login"
              className={({ isActive }) =>
                isActive ? "segment-nav__link segment-nav__link--active" : "segment-nav__link"
              }
            >
              Admin
            </NavLink>
          </nav>
          <Outlet />
        </section>
      </PageContainer>
    </div>
  );
}
