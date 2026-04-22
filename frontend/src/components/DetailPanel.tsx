import type { ReactNode } from "react";

export type DetailPanelVariant = "card" | "compact";

export function DetailPanel({
  children,
  meta,
  title,
  variant = "card"
}: {
  children: ReactNode;
  meta?: ReactNode;
  title: ReactNode;
  variant?: DetailPanelVariant;
}) {
  return (
    <details className={`detail-panel detail-panel--${variant}`}>
      <summary>
        <span className="detail-panel__title">{title}</span>
        {meta ? <span className="detail-panel__meta">{meta}</span> : null}
      </summary>
      <div className="detail-panel__content">{children}</div>
    </details>
  );
}
