import type { StatusTone } from "../contracts/status";

export function StatusBadge({ label, tone }: { label: string; tone: StatusTone }) {
  return <span className={`status-badge status-badge--${tone}`}>{label}</span>;
}

export function StatusPanel({
  detail,
  label,
  summary,
  title,
  tone
}: {
  detail?: string;
  label: string;
  summary?: string;
  title: string;
  tone: StatusTone;
}) {
  return (
    <section className="status-panel">
      <div className="status-panel__head">
        <strong>{title}</strong>
        <StatusBadge label={label} tone={tone} />
      </div>
      <p>{summary ?? "No status summary available."}</p>
      {detail ? <small>{detail}</small> : null}
    </section>
  );
}
