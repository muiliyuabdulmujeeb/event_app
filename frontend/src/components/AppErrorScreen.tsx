type AppErrorScreenProps = {
  title: string;
  message: string;
  issues?: string[];
};

export function AppErrorScreen({
  title,
  message,
  issues = [],
}: AppErrorScreenProps) {
  return (
    <main className="page-container page-container--narrow">
      <section className="state-card state-card--error app-error-screen" role="alert" aria-live="assertive">
        <p className="eyebrow">Frontend</p>
        <h2>{title}</h2>
        <p>{message}</p>

        <div className="app-error-screen__content">
          <div>
            <h3 className="app-error-screen__heading">How to fix it</h3>
            <ol className="app-error-screen__list">
              <li>Copy `frontend/.env.example` to `frontend/.env` if it does not exist.</li>
              <li>Set `VITE_API_BASE_URL` to the running backend URL, such as `http://localhost:8000`.</li>
              <li>Restart the frontend dev server or rebuild the app.</li>
            </ol>
          </div>

          {issues.length > 0 ? (
            <div>
              <h3 className="app-error-screen__heading">Validation details</h3>
              <ul className="app-error-screen__list">
                {issues.map((issue) => (
                  <li key={issue}>{issue}</li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      </section>
    </main>
  );
}
