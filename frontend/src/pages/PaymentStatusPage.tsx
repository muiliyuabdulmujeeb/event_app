import { Link, useSearchParams } from "react-router-dom";

import { PageHeader } from "../components/PageHeader";

type PaymentStatusPageProps = {
  variant: "success" | "failure";
};

export function PaymentStatusPage({ variant }: PaymentStatusPageProps) {
  const [searchParams] = useSearchParams();

  const regId = readSearchParam(searchParams, ["reg_id", "regId"]);
  const paymentReference = readSearchParam(searchParams, [
    "reference",
    "payment_reference",
    "trxref",
    "transaction_ref",
    "transactionRef",
  ]);
  const providerStatus = readSearchParam(searchParams, ["status"]);

  const lookupHref = regId
    ? `/registrations/lookup?reg_id=${encodeURIComponent(regId)}`
    : "/registrations/lookup";

  const isSuccess = variant === "success";

  return (
    <div className="page-stack">
      <section className="panel">
        <PageHeader
          eyebrow="Payments"
          title={isSuccess ? "Payment callback received" : "Payment did not complete"}
          description={
            isSuccess
              ? "This page reflects the return from your payment provider. Final registration status is still confirmed by backend processing and can be checked through registration lookup."
              : "This page reflects a failed or interrupted return from the payment provider. Use registration lookup to confirm the current backend state and any next steps."
          }
        />

        <div className="lookup-grid">
          <article className="detail-card">
            <h2 className="detail-card__title">What this means</h2>
            <div className="summary-stack">
              <p className="detail-card__text">
                {isSuccess
                  ? "A successful redirect does not independently prove that your registration is confirmed yet. The backend remains the source of truth after webhook or mock/developer payment processing completes."
                  : "A failed redirect does not always mean your registration is permanently closed. If the registration is still pending payment, you may still be able to recover a valid payment link from the lookup page."}
              </p>
              <p className="detail-card__text">
                In local mock-gateway testing, final payment state changes only after developer or test confirmation through the backend mock payment endpoints.
              </p>
            </div>
          </article>

          <article className="detail-card">
            <h2 className="detail-card__title">Callback details</h2>
            {paymentReference || providerStatus || regId ? (
              <dl className="detail-list">
                {paymentReference ? (
                  <div>
                    <dt>Payment reference</dt>
                    <dd>{paymentReference}</dd>
                  </div>
                ) : null}
                {providerStatus ? (
                  <div>
                    <dt>Provider status</dt>
                    <dd>{providerStatus}</dd>
                  </div>
                ) : null}
                {regId ? (
                  <div>
                    <dt>Registration ID</dt>
                    <dd>{regId}</dd>
                  </div>
                ) : null}
              </dl>
            ) : (
              <p className="detail-card__text">
                No trusted callback details were included in the current URL. You can still use registration lookup to review the backend state.
              </p>
            )}
          </article>
        </div>
      </section>

      <section className="panel">
        <div className="section-header">
          <h2 className="section-title">Recommended next step</h2>
          <p className="section-note">
            Use registration lookup to confirm the latest backend state before taking further action.
          </p>
        </div>

        <div className="panel__actions">
          <Link to={lookupHref} className="button-link button-link--primary">
            Review registration
          </Link>
          <Link to="/events" className="button-link">
            Browse events
          </Link>
        </div>
      </section>
    </div>
  );
}

function readSearchParam(searchParams: URLSearchParams, keys: string[]): string | null {
  for (const key of keys) {
    const value = searchParams.get(key)?.trim();
    if (value) {
      return value;
    }
  }

  return null;
}
