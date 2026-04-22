import { useEffect, useState } from "react";
import { ActionButtonGroup, type ActionButtonItem } from "../../components/ActionButtonGroup";
import { DetailPanel } from "../../components/DetailPanel";
import { EntityTable, type EntityTableColumn } from "../../components/EntityTable";
import { MetricStrip } from "../../components/MetricStrip";
import { RefreshStatus, type RefreshStatusState } from "../../components/RefreshStatus";
import { StatusBadge, StatusPanel } from "../../components/StatusWidget";
import { ViewToggle, type ViewToggleOption } from "../../components/ViewToggle";
import { fetchJson } from "../../lib/api";
import type {
  TenantDbStats,
  TenantSemanticProfile,
  TenantStatus,
  TenantStatusBlock,
  TenantsResponse
} from "./tenantTypes";
import { toneFromApi } from "./tenantTypes";

type LoadState =
  | { status: "loading"; tenants: TenantStatus[]; error?: undefined }
  | { status: "ready"; tenants: TenantStatus[]; error?: undefined }
  | { status: "error"; tenants: TenantStatus[]; error: string };

type MutationState = {
  message: string;
  status: "busy" | "success" | "error";
};

type ViewMode = "cards" | "table";

const VIEW_MODE_OPTIONS: ViewToggleOption<ViewMode>[] = [
  { label: "Cards", value: "cards" },
  { label: "Table", value: "table" }
];

const TENANT_POLL_INTERVAL_MS = 15000;

type TenantDiagnostics = {
  backfill: TenantStatusBlock;
  db: TenantDbStats;
  errorJobs: number;
  health: TenantStatusBlock;
  liveUnits: NonNullable<TenantStatus["live_units"]>;
  pendingJobs: number;
  readyProfiles: number;
  semanticProfiles: TenantSemanticProfile[];
  semanticSummary: string;
  syncHealth: TenantStatusBlock;
};

type TenantBackfillResponse = {
  action: string;
  commands?: string[][];
  dry_run?: boolean;
  ok: boolean;
  tenant: TenantStatus;
};

function numberLabel(value: number | undefined): string {
  return new Intl.NumberFormat().format(Number(value ?? 0));
}

function timeLabel(value: Date | undefined): string | undefined {
  if (!value) return undefined;

  return new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
    second: "2-digit"
  }).format(value);
}

function tenantRuntimeTone(tenant: TenantStatus): "success" | "warning" | "danger" | "neutral" {
  if (!tenant.enabled) return "warning";
  if (tenant.validation_status === "healthy") return "success";
  if (tenant.validation_status === "error") return "danger";
  return "warning";
}

function statusLabel(value: string | undefined): string {
  return String(value || "unknown").replaceAll("_", " ");
}

function tenantDiagnostics(tenant: TenantStatus): TenantDiagnostics {
  const db = tenant.db_stats ?? {};
  const syncHealth = tenant.sync_health ?? {};
  const backfill = tenant.backfill_status ?? {};
  const health = tenant.health ?? {};
  const liveUnits = tenant.live_units ?? {};
  const semanticProfiles = tenant.semantic_readiness?.profiles ?? [];
  const pendingJobs = Number(db.embedding_pending ?? 0) + Number(db.derived_pending ?? 0);
  const errorJobs = Number(db.embedding_errors ?? 0) + Number(db.derived_errors ?? 0);
  const readyProfiles = semanticProfiles.filter((profile) => profile.state === "ready").length;
  const semanticSummary = semanticProfiles.length ? `${readyProfiles}/${semanticProfiles.length} profiles ready` : "no profiles";

  return {
    backfill,
    db,
    errorJobs,
    health,
    liveUnits,
    pendingJobs,
    readyProfiles,
    semanticProfiles,
    semanticSummary,
    syncHealth
  };
}

function includesStatus(value: string | undefined, needle: string): boolean {
  return String(value ?? "")
    .toLowerCase()
    .includes(needle);
}

function tenantActions({
  diagnostics,
  mutation,
  onRunInitialSync,
  tenant
}: {
  diagnostics: TenantDiagnostics;
  mutation?: MutationState;
  onRunInitialSync: (tenant: TenantStatus) => void;
  tenant: TenantStatus;
}): ActionButtonItem[] {
  const { backfill, pendingJobs, syncHealth } = diagnostics;
  const disabledReason = "Available on the production tenant settings page until React mutations land.";
  const mutationBusy = mutation?.status === "busy";

  if (!tenant.credential_ready) {
    return [{ disabled: true, label: "Install credentials", reason: disabledReason, tone: "warning" }];
  }

  if (!tenant.db_synced) {
    return [{ disabled: true, label: "Sync tenant config", reason: disabledReason, tone: "warning" }];
  }

  if (!tenant.enabled) {
    return [{ disabled: true, label: "Activate tenant", reason: disabledReason, tone: "warning" }];
  }

  if (tenant.next_action === "run_initial_sync" || backfill.label === "needs_initial_sync") {
    return [
      {
        disabled: mutationBusy,
        label: mutationBusy ? "Initial sync running" : "Run initial sync",
        onClick: () => onRunInitialSync(tenant),
        reason: mutationBusy
          ? "Initial history sync is running. Status will refresh when the command returns."
          : "Run a bounded user-auth history sync, then refresh tenant status.",
        tone: "primary"
      }
    ];
  }

  if (
    syncHealth.tone === "bad" ||
    includesStatus(syncHealth.label, "stopped") ||
    includesStatus(syncHealth.label, "inactive")
  ) {
    return [{ disabled: true, label: "Start live sync", reason: disabledReason, tone: "primary" }];
  }

  if (syncHealth.tone === "warn") {
    return [{ disabled: true, label: "Restart live sync", reason: disabledReason, tone: "warning" }];
  }

  if (pendingJobs > 0) {
    return [
      {
        disabled: true,
        label: "Monitor backfill",
        reason: "Backfill or embedding work is still in progress.",
        tone: "neutral"
      }
    ];
  }

  return [
    {
      disabled: true,
      label: "No action needed",
      reason: "Tenant appears current from the latest status poll.",
      tone: "neutral"
    }
  ];
}

function MutationFeedback({ mutation }: { mutation?: MutationState }) {
  if (!mutation) return null;

  return (
    <div
      className={`mutation-feedback mutation-feedback--${mutation.status}`}
      role={mutation.status === "error" ? "alert" : "status"}
    >
      {mutation.message}
    </div>
  );
}

function TenantStatusRow({
  mutation,
  onRunInitialSync,
  tenant
}: {
  mutation?: MutationState;
  onRunInitialSync: (tenant: TenantStatus) => void;
  tenant: TenantStatus;
}) {
  const diagnostics = tenantDiagnostics(tenant);
  const { backfill, db, errorJobs, health, liveUnits, pendingJobs, semanticProfiles, semanticSummary, syncHealth } =
    diagnostics;

  return (
    <article className="tenant-row">
      <div className="tenant-row__identity">
        <div>
          <p className="eyebrow">Tenant</p>
          <h3>{tenant.name}</h3>
          <p>{tenant.domain || "No Slack domain recorded"}</p>
        </div>
        <div className="tenant-row__badges">
          <StatusBadge
            label={tenant.enabled ? statusLabel(tenant.validation_status ?? "enabled") : "disabled"}
            tone={tenantRuntimeTone(tenant)}
          />
          <StatusBadge
            label={tenant.credential_ready ? "credentials ready" : "credentials needed"}
            tone={tenant.credential_ready ? "success" : "warning"}
          />
          <StatusBadge
            label={tenant.db_synced ? "db synced" : "sync config"}
            tone={tenant.db_synced ? "success" : "warning"}
          />
        </div>
      </div>

      <MetricStrip
        metrics={[
          { label: "Channels", value: numberLabel(db.channels), tone: "neutral" },
          { label: "Messages", value: numberLabel(db.messages), tone: "info" },
          { label: "Files", value: numberLabel(db.files), tone: "neutral" },
          { label: "Pending Jobs", value: numberLabel(pendingJobs), tone: pendingJobs ? "warning" : "success" }
        ]}
      />

      <div className="tenant-row__grid">
        <StatusPanel
          detail={backfill.detail}
          label={statusLabel(backfill.label)}
          summary={backfill.summary}
          title="Backfill"
          tone={toneFromApi(backfill.tone)}
        />
        <StatusPanel
          detail={syncHealth.detail}
          label={statusLabel(syncHealth.label)}
          summary={syncHealth.summary}
          title="Live Sync"
          tone={toneFromApi(syncHealth.tone)}
        />
        <StatusPanel
          detail={health.detail}
          label={statusLabel(tenant.next_action)}
          summary={health.summary}
          title="Health"
          tone={toneFromApi(health.tone)}
        />
      </div>

      <ActionButtonGroup
        actions={tenantActions({ diagnostics, mutation, onRunInitialSync, tenant })}
        ariaLabel={`${tenant.name} recommended actions`}
      />
      <MutationFeedback mutation={mutation} />

      <DetailPanel
        meta={
          <>
            live {liveUnits.webhooks ?? "unknown"} / daemon {liveUnits.daemon ?? "unknown"} · text{" "}
            {numberLabel(db.attachment_text)} / OCR {numberLabel(db.ocr_text)} · {semanticSummary}
          </>
        }
        title="Details and readiness"
      >
        <div>
          <strong>Live units</strong>
          <p>
            webhooks {liveUnits.webhooks ?? "unknown"} / daemon {liveUnits.daemon ?? "unknown"}
          </p>
        </div>
        <div>
          <strong>Text and embeddings</strong>
          <p>
            attachment text {numberLabel(db.attachment_text)} / OCR {numberLabel(db.ocr_text)} / errors{" "}
            {numberLabel(errorJobs)}
          </p>
        </div>
        <div>
          <strong>Semantic readiness</strong>
          <p>{tenant.semantic_readiness?.summary ?? "No semantic readiness summary available."}</p>
          <div className="chip-row">
            {semanticProfiles.length ? (
              semanticProfiles.map((profile) => (
                <StatusBadge
                  key={profile.name ?? profile.state}
                  label={`${profile.name ?? "profile"}: ${statusLabel(profile.state)}`}
                  tone={toneFromApi(profile.tone)}
                />
              ))
            ) : (
              <StatusBadge label="no profiles" tone="neutral" />
            )}
          </div>
        </div>
      </DetailPanel>
    </article>
  );
}

function TenantStatusTable({
  mutations,
  onRunInitialSync,
  tenants
}: {
  mutations: Record<string, MutationState>;
  onRunInitialSync: (tenant: TenantStatus) => void;
  tenants: TenantStatus[];
}) {
  const columns: EntityTableColumn<TenantStatus>[] = [
    {
      header: "Tenant",
      id: "tenant",
      render: (tenant) => (
        <>
          <strong>{tenant.name}</strong>
          <small>{tenant.domain || "No Slack domain recorded"}</small>
        </>
      ),
      rowHeader: true
    },
    {
      header: "Readiness",
      id: "readiness",
      render: (tenant) => (
        <div className="entity-table__chips">
          <StatusBadge
            label={tenant.enabled ? statusLabel(tenant.validation_status ?? "enabled") : "disabled"}
            tone={tenantRuntimeTone(tenant)}
          />
          <StatusBadge
            label={tenant.credential_ready ? "credentials" : "credentials needed"}
            tone={tenant.credential_ready ? "success" : "warning"}
          />
          <StatusBadge
            label={tenant.db_synced ? "db synced" : "sync config"}
            tone={tenant.db_synced ? "success" : "warning"}
          />
        </div>
      )
    },
    {
      header: "DB Stats",
      id: "db-stats",
      render: (tenant) => {
        const { db, pendingJobs } = tenantDiagnostics(tenant);
        return (
          <>
            <strong>{numberLabel(db.messages)}</strong>
            <small>
              {numberLabel(db.channels)} channels / {numberLabel(db.files)} files / {numberLabel(pendingJobs)} pending
            </small>
          </>
        );
      }
    },
    {
      header: "Backfill",
      id: "backfill",
      render: (tenant) => {
        const { backfill } = tenantDiagnostics(tenant);
        return (
          <>
            <StatusBadge label={statusLabel(backfill.label)} tone={toneFromApi(backfill.tone)} />
            <small>{backfill.summary ?? "No backfill summary."}</small>
          </>
        );
      }
    },
    {
      header: "Live Sync",
      id: "live-sync",
      render: (tenant) => {
        const { syncHealth } = tenantDiagnostics(tenant);
        return (
          <>
            <StatusBadge label={statusLabel(syncHealth.label)} tone={toneFromApi(syncHealth.tone)} />
            <small>{syncHealth.summary ?? "No live-sync summary."}</small>
          </>
        );
      }
    },
    {
      header: "Health",
      id: "health",
      render: (tenant) => {
        const { health } = tenantDiagnostics(tenant);
        return (
          <>
            <StatusBadge label={statusLabel(tenant.next_action)} tone={toneFromApi(health.tone)} />
            <small>{health.summary ?? "No health summary."}</small>
          </>
        );
      }
    },
    {
      header: "Semantic",
      id: "semantic",
      render: (tenant) => {
        const { semanticSummary } = tenantDiagnostics(tenant);
        return (
          <>
            <strong>{semanticSummary}</strong>
            <small>{tenant.semantic_readiness?.summary ?? "No semantic readiness summary."}</small>
          </>
        );
      }
    },
    {
      header: "Details",
      id: "details",
      render: (tenant) => {
        const diagnostics = tenantDiagnostics(tenant);
        const { db, errorJobs, liveUnits, semanticProfiles } = diagnostics;
        return (
          <DetailPanel title="Inspect" variant="compact">
            <ActionButtonGroup
              actions={tenantActions({
                diagnostics,
                mutation: mutations[tenant.name],
                onRunInitialSync,
                tenant
              })}
              ariaLabel={`${tenant.name} recommended actions`}
            />
            <MutationFeedback mutation={mutations[tenant.name]} />
            <p>
              live webhooks {liveUnits.webhooks ?? "unknown"} / daemon {liveUnits.daemon ?? "unknown"}
            </p>
            <p>
              attachment text {numberLabel(db.attachment_text)} / OCR {numberLabel(db.ocr_text)} / errors{" "}
              {numberLabel(errorJobs)}
            </p>
            <div className="entity-table__chips">
              {semanticProfiles.length ? (
                semanticProfiles.map((profile) => (
                  <StatusBadge
                    key={profile.name ?? profile.state}
                    label={`${profile.name ?? "profile"}: ${statusLabel(profile.state)}`}
                    tone={toneFromApi(profile.tone)}
                  />
                ))
              ) : (
                <StatusBadge label="no profiles" tone="neutral" />
              )}
            </div>
          </DetailPanel>
        );
      }
    }
  ];

  return (
    <EntityTable
      ariaLabel="Compact tenant status table"
      columns={columns}
      getRowKey={(tenant) => tenant.name}
      rows={tenants}
    />
  );
}

export function TenantWorkbench() {
  const [state, setState] = useState<LoadState>({ status: "loading", tenants: [] });
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | undefined>();
  const [mutations, setMutations] = useState<Record<string, MutationState>>({});
  const [refreshState, setRefreshState] = useState<RefreshStatusState>("loading");
  const [viewMode, setViewMode] = useState<ViewMode>("cards");

  useEffect(() => {
    let cancelled = false;

    async function loadTenants() {
      try {
        const payload = await fetchJson<TenantsResponse>("/v1/tenants");
        if (!cancelled) {
          setState({ status: "ready", tenants: payload.tenants ?? [] });
          setLastUpdatedAt(new Date());
          setRefreshState("idle");
        }
      } catch (error) {
        if (!cancelled) {
          setState({
            error: error instanceof Error ? error.message : "Tenant status failed to load.",
            status: "error",
            tenants: []
          });
          setRefreshState("error");
        }
      }
    }

    void loadTenants();
    const interval = window.setInterval(() => {
      setRefreshState("loading");
      void loadTenants();
    }, TENANT_POLL_INTERVAL_MS);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  async function refreshTenants() {
    setRefreshState("loading");

    try {
      const payload = await fetchJson<TenantsResponse>("/v1/tenants");
      setState({ status: "ready", tenants: payload.tenants ?? [] });
      setLastUpdatedAt(new Date());
      setRefreshState("idle");
    } catch (error) {
      setState((current) => ({
        error: error instanceof Error ? error.message : "Tenant status failed to load.",
        status: "error",
        tenants: current.tenants
      }));
      setRefreshState("error");
    }
  }

  async function runInitialSync(tenant: TenantStatus) {
    setMutations((current) => ({
      ...current,
      [tenant.name]: {
        message: "Initial history sync requested. Waiting for the bounded backfill command to return...",
        status: "busy"
      }
    }));

    try {
      const payload = await fetchJson<TenantBackfillResponse>(
        `/v1/tenants/${encodeURIComponent(tenant.name)}/backfill`,
        {
          body: JSON.stringify({
            auth_mode: "user",
            channel_limit: 10,
            include_files: false,
            include_messages: true
          }),
          headers: { "content-type": "application/json" },
          method: "POST"
        }
      );

      setMutations((current) => ({
        ...current,
        [tenant.name]: {
          message: `Initial history sync ${payload.action || "backfill"} completed for ${payload.tenant.name}. Refreshing status...`,
          status: "success"
        }
      }));
      await refreshTenants();
    } catch (error) {
      setMutations((current) => ({
        ...current,
        [tenant.name]: {
          message: error instanceof Error ? error.message : "Initial history sync failed.",
          status: "error"
        }
      }));
      await refreshTenants();
    }
  }

  const enabledCount = state.tenants.filter((tenant) => tenant.enabled).length;
  const readyCount = state.tenants.filter((tenant) => tenant.credential_ready && tenant.db_synced).length;
  const pendingJobs = state.tenants.reduce((total, tenant) => {
    const db = tenant.db_stats ?? {};
    return total + Number(db.embedding_pending ?? 0) + Number(db.derived_pending ?? 0);
  }, 0);

  return (
    <section className="workbench" aria-labelledby="tenant-workbench-heading">
      <div className="workbench__intro">
        <div>
          <p className="eyebrow">Read-only adapter</p>
          <h2 id="tenant-workbench-heading">Tenant Status Workbench</h2>
          <p>
            This React preview reads the existing tenant-status API and keeps setup, activation,
            live-sync controls, and backfill actions on the production tenant settings page.
          </p>
        </div>
        <a className="button button--primary" href="/settings/tenants">
          Manage tenants
        </a>
      </div>

      <MetricStrip
        metrics={[
          { label: "Tenants", value: numberLabel(state.tenants.length), tone: "neutral" },
          { label: "Enabled", value: numberLabel(enabledCount), tone: enabledCount ? "success" : "warning" },
          { label: "Ready", value: numberLabel(readyCount), tone: readyCount ? "success" : "warning" },
          { label: "Pending Jobs", value: numberLabel(pendingJobs), tone: pendingJobs ? "warning" : "success" }
        ]}
      />

      <RefreshStatus
        intervalSeconds={TENANT_POLL_INTERVAL_MS / 1000}
        lastUpdatedLabel={timeLabel(lastUpdatedAt)}
        onRefresh={() => {
          void refreshTenants();
        }}
        state={refreshState}
      />

      {state.status === "loading" ? <div className="empty-state">Loading tenant status...</div> : null}
      {state.status === "error" ? (
        <div className="empty-state empty-state--danger" role="alert">
          {state.error}
        </div>
      ) : null}
      {state.status === "ready" && state.tenants.length === 0 ? (
        <div className="empty-state">No tenants are configured yet.</div>
      ) : null}

      {state.tenants.length ? (
        <ViewToggle ariaLabel="Tenant view mode" onChange={setViewMode} options={VIEW_MODE_OPTIONS} value={viewMode} />
      ) : null}

      {viewMode === "cards" ? (
        <div className="tenant-list">
          {state.tenants.map((tenant) => (
            <TenantStatusRow
              key={tenant.name}
              mutation={mutations[tenant.name]}
              onRunInitialSync={runInitialSync}
              tenant={tenant}
            />
          ))}
        </div>
      ) : (
        <TenantStatusTable mutations={mutations} onRunInitialSync={runInitialSync} tenants={state.tenants} />
      )}
    </section>
  );
}
