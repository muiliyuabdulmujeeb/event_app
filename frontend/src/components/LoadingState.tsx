type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label = "Loading…" }: LoadingStateProps) {
  return (
    <div className="state-card" role="status" aria-live="polite">
      <p>{label}</p>
    </div>
  );
}
