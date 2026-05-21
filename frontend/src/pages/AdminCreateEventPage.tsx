import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { createAdminEvent } from "../api/adminEvents";
import { AdminEventForm } from "../components/AdminEventForm";
import { PageHeader } from "../components/PageHeader";
import { ApiError } from "../lib/apiError";
import { queryKeys } from "../lib/queryKeys";
import type { AdminEventCreateRequest, AdminEventDetail } from "../types/adminEvents";

export function AdminCreateEventPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const createMutation = useMutation<AdminEventDetail, ApiError, AdminEventCreateRequest>({
    mutationFn: createAdminEvent,
  });

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Admin"
          title="Create event"
          description="Define the event details, pricing, capacity rules, and any custom attendee fields required at registration time."
        />
      </section>

      <section className="panel">
        <AdminEventForm
          backHref="/admin/events"
          isSubmitting={createMutation.isPending}
          mode="create"
          onSubmit={async (payload) => {
            const response = await createMutation.mutateAsync(payload as AdminEventCreateRequest);
            queryClient.setQueryData(queryKeys.adminEvents.detail(response.id), response);
            void queryClient.invalidateQueries({ queryKey: queryKeys.adminEvents.all });
            navigate(`/admin/events/${response.id}/edit`, { replace: true });
          }}
          submitLabel="Create event"
        />
      </section>
    </div>
  );
}
