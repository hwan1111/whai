export default function LoadingSpinner({ label = '불러오는 중...', size = 30, compact = false }) {
  return (
    <div
      className={`loading-spinner-wrap${compact ? ' loading-spinner-compact' : ''}`}
      role="status"
      aria-live="polite"
    >
      <span className="loading-spinner" style={{ width: size, height: size }} aria-hidden="true" />
      {label && <span className="loading-spinner-label">{label}</span>}
    </div>
  );
}
