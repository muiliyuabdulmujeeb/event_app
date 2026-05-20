type ErrorStateProps = {
  title?: string;
  message: string;
};

export function ErrorState({ title = "Something went wrong", message }: ErrorStateProps) {
  return (
    <section className="state-card state-card--error" role="alert">
      <h2>{title}</h2>
      <p>{message}</p>
    </section>
  );
}
