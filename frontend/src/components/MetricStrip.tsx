export interface Metric {
  label: string;
  value: string;
  tone?: "neutral" | "success" | "warning" | "danger" | "info";
}

export interface MetricStripProps {
  metrics: Metric[];
}

export function MetricStrip({ metrics }: MetricStripProps) {
  return (
    <div className="metric-strip">
      {metrics.map((metric) => (
        <div className={`metric-pill metric-pill--${metric.tone ?? "neutral"}`} key={metric.label}>
          <span>{metric.label}</span>
          <strong>{metric.value}</strong>
        </div>
      ))}
    </div>
  );
}
