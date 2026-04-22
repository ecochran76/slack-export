export type RefreshStatusState = "idle" | "loading" | "error";

export function RefreshStatus({
  intervalSeconds,
  lastUpdatedLabel,
  onRefresh,
  state
}: {
  intervalSeconds?: number;
  lastUpdatedLabel?: string;
  onRefresh: () => void;
  state: RefreshStatusState;
}) {
  const isLoading = state === "loading";

  return (
    <div className={`refresh-status refresh-status--${state}`} aria-live="polite">
      <div>
        <span className="refresh-status__label">{isLoading ? "Refreshing status" : "Status refreshed"}</span>
        <small>
          {lastUpdatedLabel ? `Last updated ${lastUpdatedLabel}` : "Waiting for first status poll"}
          {intervalSeconds ? ` · auto every ${intervalSeconds}s` : null}
        </small>
      </div>
      <button className="button refresh-status__button" disabled={isLoading} onClick={onRefresh} type="button">
        {isLoading ? "Refreshing..." : "Refresh now"}
      </button>
    </div>
  );
}
