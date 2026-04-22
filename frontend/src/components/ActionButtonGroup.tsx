export type ActionButtonTone = "primary" | "neutral" | "warning" | "danger";

export type ActionButtonItem = {
  disabled?: boolean;
  label: string;
  onClick?: () => void;
  reason?: string;
  tone?: ActionButtonTone;
};

export function ActionButtonGroup({
  actions,
  ariaLabel
}: {
  actions: ActionButtonItem[];
  ariaLabel: string;
}) {
  return (
    <div className="action-group" aria-label={ariaLabel}>
      {actions.map((action) => (
        <button
          className={`button action-group__button action-group__button--${action.tone ?? "neutral"}`}
          disabled={action.disabled ?? false}
          key={action.label}
          onClick={action.onClick}
          title={action.reason}
          type="button"
        >
          <span>{action.label}</span>
          {action.reason ? <small>{action.reason}</small> : null}
        </button>
      ))}
    </div>
  );
}
