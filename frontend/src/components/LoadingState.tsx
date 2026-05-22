type LoadingStateProps = {
  label?: string;
};

export function LoadingState({ label = "Loading..." }: LoadingStateProps) {
  return (
    <div className="state-card" role="status" aria-live="polite" aria-atomic="true">
      <p>{label}</p>
    </div>
  );
}
