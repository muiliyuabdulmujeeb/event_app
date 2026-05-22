import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";

import { listAdminStaffAccounts } from "../api/adminStaff";
import { EmptyState } from "../components/EmptyState";
import { ErrorState } from "../components/ErrorState";
import { LoadingState } from "../components/LoadingState";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { formatDateTime } from "../lib/date";
import { queryKeys } from "../lib/queryKeys";
import type { AdminStaffAccountSummary, StaffRole } from "../types/adminStaff";

export function AdminStaffPage() {
  const staffQuery = useQuery<AdminStaffAccountSummary[], ApiError>({
    queryKey: queryKeys.adminStaff.all,
    queryFn: ({ signal }) => listAdminStaffAccounts(signal),
  });

  if (staffQuery.isPending) {
    return <LoadingState label="Loading staff accounts..." />;
  }

  if (staffQuery.isError) {
    return (
      <ErrorState
        title="Could not load staff accounts"
        message={staffQuery.error.message}
      />
    );
  }

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Staff management"
          description="Review staff and admin accounts, then open the account detail view to update activation, role, and event-access settings."
        />
      </section>

      {staffQuery.data.length === 0 ? (
        <EmptyState
          title="No staff accounts found"
          description="Accounts will appear here once the backend has staff or admin records to manage."
        />
      ) : (
        <section className="panel">
          <div className="section-header">
            <div>
              <h2 className="section-title">Accounts</h2>
              <p className="section-note">
                {staffQuery.data.length} account{staffQuery.data.length === 1 ? "" : "s"} loaded from the admin staff endpoint.
              </p>
            </div>
          </div>

          <div className="table-wrap">
            <table className="data-table">
              <thead>
                <tr>
                  <th scope="col">Account</th>
                  <th scope="col">Role</th>
                  <th scope="col">Status</th>
                  <th scope="col">Created</th>
                  <th scope="col">Actions</th>
                </tr>
              </thead>
              <tbody>
                {staffQuery.data.map((account) => (
                  <tr key={account.id}>
                    <td>
                      <div className="table-cell-stack">
                        <strong>{account.email}</strong>
                        <span>{account.id}</span>
                      </div>
                    </td>
                    <td>{formatRole(account.role)}</td>
                    <td>
                      <span
                        className={
                          account.is_active
                            ? "status-pill status-pill--success"
                            : "status-pill status-pill--neutral"
                        }
                      >
                        {account.is_active ? "Active" : "Disabled"}
                      </span>
                    </td>
                    <td>{formatDateTime(account.created_at)}</td>
                    <td>
                      <Link to={`/admin/staff/${account.id}`} className="button-link">
                        Manage account
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}

function formatRole(role: StaffRole): string {
  return role === "admin" ? "Admin" : "Staff";
}
