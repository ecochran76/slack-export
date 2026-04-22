export type ViewToggleOption<Value extends string> = {
  label: string;
  value: Value;
};

export function ViewToggle<Value extends string>({
  ariaLabel,
  onChange,
  options,
  value
}: {
  ariaLabel: string;
  onChange: (value: Value) => void;
  options: ViewToggleOption<Value>[];
  value: Value;
}) {
  return (
    <div className="view-toggle" aria-label={ariaLabel}>
      {options.map((option) => (
        <button
          aria-pressed={value === option.value}
          className="button button--toggle"
          key={option.value}
          onClick={() => onChange(option.value)}
          type="button"
        >
          {option.label}
        </button>
      ))}
    </div>
  );
}
