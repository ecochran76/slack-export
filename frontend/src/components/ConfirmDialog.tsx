import { useEffect, useId, useState } from "react";

export type ConfirmDialogTone = "neutral" | "danger";

export function ConfirmDialog({
  confirmLabel,
  details,
  expectedText,
  message,
  onCancel,
  onConfirm,
  open,
  title,
  tone = "neutral"
}: {
  confirmLabel: string;
  details?: string;
  expectedText?: string;
  message: string;
  onCancel: () => void;
  onConfirm: () => void;
  open: boolean;
  title: string;
  tone?: ConfirmDialogTone;
}) {
  const [confirmationText, setConfirmationText] = useState("");
  const titleId = useId();
  const descriptionId = useId();
  const canConfirm = !expectedText || confirmationText === expectedText;

  useEffect(() => {
    if (!open) {
      setConfirmationText("");
    }
  }, [open]);

  if (!open) return null;

  return (
    <div className="confirm-dialog" role="presentation">
      <div
        aria-describedby={descriptionId}
        aria-labelledby={titleId}
        aria-modal="true"
        className={`confirm-dialog__panel confirm-dialog__panel--${tone}`}
        role="dialog"
      >
        <div className="confirm-dialog__header">
          <p className="eyebrow">Confirm action</p>
          <h3 id={titleId}>{title}</h3>
        </div>
        <div className="confirm-dialog__body" id={descriptionId}>
          <p>{message}</p>
          {details ? <small>{details}</small> : null}
        </div>
        {expectedText ? (
          <label className="confirm-dialog__field">
            <span>Type {expectedText} to confirm</span>
            <input
              autoFocus
              onChange={(event) => setConfirmationText(event.target.value)}
              value={confirmationText}
            />
          </label>
        ) : null}
        <div className="confirm-dialog__actions">
          <button className="button confirm-dialog__cancel" onClick={onCancel} type="button">
            Cancel
          </button>
          <button
            className={`button confirm-dialog__confirm confirm-dialog__confirm--${tone}`}
            disabled={!canConfirm}
            onClick={onConfirm}
            type="button"
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
