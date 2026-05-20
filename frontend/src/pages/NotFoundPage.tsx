import { NavLink } from "react-router-dom";

import { PageHeader } from "../components/PageHeader";

export function NotFoundPage() {
  return (
    <section className="panel">
      <PageHeader
        eyebrow="Not Found"
        title="This page does not exist"
        description="The requested route could not be found in the current frontend workspace."
      />
      <NavLink to="/events" className="button-link">
        Go to events
      </NavLink>
    </section>
  );
}
