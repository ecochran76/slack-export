export type ActionButtonTone = "primary" | "neutral" | "warning" | "danger";
export type ActionButtonCategory = "next" | "maintenance" | "guarded";

export type ActionButtonItem = {
  category?: ActionButtonCategory;
  disabled?: boolean;
  label: string;
  onClick?: () => void;
  reason?: string;
  tone?: ActionButtonTone;
};

const CATEGORY_ORDER: ActionButtonCategory[] = ["next", "maintenance", "guarded"];

const CATEGORY_LABELS: Record<ActionButtonCategory, string> = {
  guarded: "Guarded",
  maintenance: "Maintenance",
  next: "Next step"
};

export function ActionButtonGroup({
  actions,
  ariaLabel
}: {
  actions: ActionButtonItem[];
  ariaLabel: string;
}) {
  const groupedActions = CATEGORY_ORDER.map((category) => ({
    actions: actions.filter((action) => (action.category ?? "next") === category),
    category
  })).filter((group) => group.actions.length);
  const showCategoryLabels = groupedActions.length > 1;

  return (
    <div className="action-group" aria-label={ariaLabel}>
      {groupedActions.map(({ actions: categoryActions, category }) => (
        <section className={`action-group__section action-group__section--${category}`} key={category}>
          {showCategoryLabels ? <p className="action-group__section-label">{CATEGORY_LABELS[category]}</p> : null}
          <div className="action-group__items">
            {categoryActions.map((action) => (
              <button
                className={`button action-group__button action-group__button--${action.tone ?? "neutral"}`}
                disabled={action.disabled ?? false}
                key={`${category}:${action.label}`}
                onClick={action.onClick}
                title={action.reason}
                type="button"
              >
                <span>{action.label}</span>
                {action.reason ? <small>{action.reason}</small> : null}
              </button>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}
