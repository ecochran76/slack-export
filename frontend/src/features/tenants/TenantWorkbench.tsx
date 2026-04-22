import { useEffect, useState } from "react";
import { ActionButtonGroup, type ActionButtonItem } from "../../components/ActionButtonGroup";
import { ConfirmDialog } from "../../components/ConfirmDialog";
import { DetailPanel } from "../../components/DetailPanel";
import { EntityTable, type EntityTableColumn } from "../../components/EntityTable";
import { MetricStrip } from "../../components/MetricStrip";
import { RefreshStatus, type RefreshStatusState } from "../../components/RefreshStatus";
import { StatusBadge, StatusPanel } from "../../components/StatusWidget";
import { ViewToggle, type ViewToggleOption } from "../../components/ViewToggle";
import { fetchJson } from "../../lib/api";
import { runTrackedMutation, type MutationState, type MutationStateMap } from "../../lib/trackedMutation";
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

type TenantActivateResponse = {
  backup_path?: string;
  changed: boolean;
  config_path: string;
  dry_run?: boolean;
  live_unit_command?: string[];
  live_units_installed: boolean;
  ok: boolean;
  tenant: TenantStatus;
};

type TenantActivationSequenceResponse = {
  activation: TenantActivateResponse;
  backfill: TenantBackfillResponse;
};

type TenantCredentialsResponse = {
  backup_path?: string;
  changed: boolean;
  dotenv_path: string;
  dry_run?: boolean;
  installed_keys: string[];
  ok: boolean;
  skipped_keys: string[];
  tenant: TenantStatus;
};

type TenantLiveResponse = {
  action: string;
  commands?: string[][];
  dry_run?: boolean;
  ok: boolean;
  tenant: TenantStatus;
};

type TenantLiveAction = "start" | "restart" | "stop";

type CredentialField = {
  field: string;
  label: string;
  required: boolean;
};

const CREDENTIAL_FIELDS: CredentialField[] = [
  { field: "token", label: "Bot token", required: true },
  { field: "outbound_token", label: "Write bot token", required: true },
  { field: "app_token", label: "App token", required: true },
  { field: "signing_secret", label: "Signing secret", required: true },
  { field: "team_id", label: "Team ID", required: false },
  { field: "user_token", label: "User token", required: false },
  { field: "outbound_user_token", label: "Write user token", required: false }
];

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

function requestInitialSync(tenantName: string): Promise<TenantBackfillResponse> {
  return fetchJson<TenantBackfillResponse>(`/v1/tenants/${encodeURIComponent(tenantName)}/backfill`, {
    body: JSON.stringify({
      auth_mode: "user",
      channel_limit: 10,
      include_files: false,
      include_messages: true
    }),
    headers: { "content-type": "application/json" },
    method: "POST"
  });
}

function tenantActions({
  diagnostics,
  onActivateTenant,
  mutation,
  onRequestCredentials,
  onRestartLiveSync,
  onRequestStopLiveSync,
  onRunInitialSync,
  onStartLiveSync,
  tenant
}: {
  diagnostics: TenantDiagnostics;
  mutation?: MutationState;
  onActivateTenant: (tenant: TenantStatus) => void;
  onRequestCredentials: (tenant: TenantStatus) => void;
  onRestartLiveSync: (tenant: TenantStatus) => void;
  onRequestStopLiveSync: (tenant: TenantStatus) => void;
  onRunInitialSync: (tenant: TenantStatus) => void;
  onStartLiveSync: (tenant: TenantStatus) => void;
  tenant: TenantStatus;
}): ActionButtonItem[] {
  const { backfill, liveUnits, pendingJobs, syncHealth } = diagnostics;
  const disabledReason = "Available on the production tenant settings page until React mutations land.";
  const mutationBusy = mutation?.status === "busy";
  const unitsActive = liveUnits.webhooks === "active" || liveUnits.daemon === "active";

  if (!tenant.credential_ready) {
    return [
      {
        disabled: mutationBusy,
        label: mutationBusy ? "Installing credentials" : "Install credentials",
        onClick: () => onRequestCredentials(tenant),
        reason: mutationBusy
          ? "Credential installation is running. Status will refresh when the command returns."
          : "Install Slack credentials into the configured local dotenv file.",
        tone: "primary"
      }
    ];
  }

  if (!tenant.db_synced) {
    return [{ disabled: true, label: "Sync tenant config", reason: disabledReason, tone: "warning" }];
  }

  if (!tenant.enabled) {
    if (tenant.next_action === "ready_to_activate") {
      return [
        {
          disabled: mutationBusy,
          label: mutationBusy ? "Activating tenant" : "Activate tenant",
          onClick: () => onActivateTenant(tenant),
          reason: mutationBusy
            ? "Activation is running. Status will refresh when the sequence returns."
            : "Enable the tenant, install live sync, and start bounded initial sync.",
          tone: "primary"
        }
      ];
    }

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

  if (tenant.next_action === "start_live_sync") {
    return [
      {
        disabled: mutationBusy,
        label: mutationBusy ? "Starting live sync" : "Start live sync",
        onClick: () => onStartLiveSync(tenant),
        reason: mutationBusy
          ? "Live sync start is running. Status will refresh when the command returns."
          : "Install and start the tenant live-sync units, then refresh tenant status.",
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

  if (syncHealth.tone === "warn" && unitsActive) {
    return [
      {
        disabled: mutationBusy,
        label: mutationBusy ? "Restarting live sync" : "Restart live sync",
        onClick: () => onRestartLiveSync(tenant),
        reason: mutationBusy
          ? "Live sync restart is running. Status will refresh when the command returns."
          : "Restart active live-sync units, then refresh tenant status.",
        tone: "warning"
      }
    ];
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

  const actions: ActionButtonItem[] = [
    {
      disabled: true,
      label: "No action needed",
      reason: "Tenant appears current from the latest status poll.",
      tone: "neutral"
    }
  ];

  if (unitsActive) {
    actions.push({
      disabled: mutationBusy,
      label: mutationBusy ? "Stopping live sync" : "Stop live sync",
      onClick: () => onRequestStopLiveSync(tenant),
      reason: mutationBusy
        ? "Live sync stop is running. Status will refresh when the command returns."
        : "Stop active live-sync units after typed confirmation.",
      tone: "danger"
    });
  }

  return actions;
}

function CredentialInstallForm({
  busy,
  onCancel,
  onSubmit,
  tenant
}: {
  busy: boolean;
  onCancel: () => void;
  onSubmit: (tenant: TenantStatus, credentials: Record<string, string>) => void;
  tenant: TenantStatus;
}) {
  return (
    <form
      className="credential-form"
      onSubmit={(event) => {
        event.preventDefault();
        const form = event.currentTarget;
        const formData = new FormData(form);
        const credentials = Object.fromEntries(
          CREDENTIAL_FIELDS.map(({ field }) => [field, String(formData.get(field) ?? "").trim()]).filter(
            ([, value]) => value
          )
        );
        onSubmit(tenant, credentials);
        form.reset();
      }}
    >
      <div className="credential-form__intro">
        <strong>Install Slack credentials for {tenant.name}</strong>
        <small>Values are sent once to the local API and are not echoed back in the UI.</small>
      </div>
      <div className="credential-form__grid">
        {CREDENTIAL_FIELDS.map((field) => (
          <label key={field.field}>
            <span>
              {field.label}
              {field.required ? " *" : ""}
            </span>
            <input
              autoComplete="off"
              disabled={busy}
              name={field.field}
              placeholder={field.required ? "required" : "optional"}
              type="password"
            />
          </label>
        ))}
      </div>
      <div className="credential-form__actions">
        <button className="button credential-form__cancel" disabled={busy} onClick={onCancel} type="button">
          Cancel
        </button>
        <button className="button button--primary" disabled={busy} type="submit">
          {busy ? "Installing..." : "Install credentials"}
        </button>
      </div>
    </form>
  );
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
  credentialFormOpen,
  mutation,
  onActivateTenant,
  onCancelCredentials,
  onInstallCredentials,
  onRequestCredentials,
  onRestartLiveSync,
  onRequestStopLiveSync,
  onRunInitialSync,
  onStartLiveSync,
  tenant
}: {
  credentialFormOpen: boolean;
  mutation?: MutationState;
  onActivateTenant: (tenant: TenantStatus) => void;
  onCancelCredentials: () => void;
  onInstallCredentials: (tenant: TenantStatus, credentials: Record<string, string>) => void;
  onRequestCredentials: (tenant: TenantStatus) => void;
  onRestartLiveSync: (tenant: TenantStatus) => void;
  onRequestStopLiveSync: (tenant: TenantStatus) => void;
  onRunInitialSync: (tenant: TenantStatus) => void;
  onStartLiveSync: (tenant: TenantStatus) => void;
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
        actions={tenantActions({
          diagnostics,
          mutation,
          onActivateTenant,
          onRequestCredentials,
          onRestartLiveSync,
          onRequestStopLiveSync,
          onRunInitialSync,
          onStartLiveSync,
          tenant
        })}
        ariaLabel={`${tenant.name} recommended actions`}
      />
      {credentialFormOpen ? (
        <CredentialInstallForm
          busy={mutation?.status === "busy"}
          onCancel={onCancelCredentials}
          onSubmit={onInstallCredentials}
          tenant={tenant}
        />
      ) : null}
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
  credentialFormTenant,
  mutations,
  onActivateTenant,
  onCancelCredentials,
  onInstallCredentials,
  onRequestCredentials,
  onRestartLiveSync,
  onRequestStopLiveSync,
  onRunInitialSync,
  onStartLiveSync,
  tenants
}: {
  credentialFormTenant?: string;
  mutations: MutationStateMap;
  onActivateTenant: (tenant: TenantStatus) => void;
  onCancelCredentials: () => void;
  onInstallCredentials: (tenant: TenantStatus, credentials: Record<string, string>) => void;
  onRequestCredentials: (tenant: TenantStatus) => void;
  onRestartLiveSync: (tenant: TenantStatus) => void;
  onRequestStopLiveSync: (tenant: TenantStatus) => void;
  onRunInitialSync: (tenant: TenantStatus) => void;
  onStartLiveSync: (tenant: TenantStatus) => void;
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
                onActivateTenant,
                onRequestCredentials,
                onRestartLiveSync,
                onRequestStopLiveSync,
                onRunInitialSync,
                onStartLiveSync,
                tenant
              })}
              ariaLabel={`${tenant.name} recommended actions`}
            />
            {credentialFormTenant === tenant.name ? (
              <CredentialInstallForm
                busy={mutations[tenant.name]?.status === "busy"}
                onCancel={onCancelCredentials}
                onSubmit={onInstallCredentials}
                tenant={tenant}
              />
            ) : null}
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
  const [credentialFormTenant, setCredentialFormTenant] = useState<string | undefined>();
  const [lastUpdatedAt, setLastUpdatedAt] = useState<Date | undefined>();
  const [mutations, setMutations] = useState<MutationStateMap>({});
  const [pendingStopTenant, setPendingStopTenant] = useState<TenantStatus | undefined>();
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
    await runTrackedMutation<TenantBackfillResponse>({
      afterSettled: refreshTenants,
      busyMessage: "Initial history sync requested. Waiting for the bounded backfill command to return...",
      errorMessage: (error) => (error instanceof Error ? error.message : "Initial history sync failed."),
      key: tenant.name,
      run: () => requestInitialSync(tenant.name),
      setMutations,
      successMessage: (payload) =>
        `Initial history sync ${payload.action || "backfill"} completed for ${payload.tenant.name}. Refreshing status...`
    });
  }

  async function activateTenant(tenant: TenantStatus) {
    await runTrackedMutation<TenantActivationSequenceResponse>({
      afterSettled: refreshTenants,
      busyMessage: "Activating tenant, installing live sync, and starting bounded initial history sync...",
      errorMessage: (error) => (error instanceof Error ? error.message : "Tenant activation failed."),
      key: tenant.name,
      run: async () => {
        const activation = await fetchJson<TenantActivateResponse>(
          `/v1/tenants/${encodeURIComponent(tenant.name)}/activate`,
          {
            body: JSON.stringify({}),
            headers: { "content-type": "application/json" },
            method: "POST"
          }
        );
        let backfill: TenantBackfillResponse;
        try {
          backfill = await requestInitialSync(tenant.name);
        } catch (error) {
          const message = error instanceof Error ? error.message : "Initial sync failed.";
          throw new Error(`Tenant activated, but initial sync failed: ${message}`);
        }
        return { activation, backfill };
      },
      setMutations,
      successMessage: ({ activation, backfill }) =>
        `Activated ${activation.tenant.name}. Initial history sync ${backfill.action || "backfill"} started. Refreshing status...`
    });
  }

  async function installCredentials(tenant: TenantStatus, credentials: Record<string, string>) {
    if (!Object.keys(credentials).length) {
      setMutations((current) => ({
        ...current,
        [tenant.name]: {
          message: "Enter at least one credential value before installing.",
          status: "error"
        }
      }));
      return;
    }

    const payload = await runTrackedMutation<TenantCredentialsResponse>({
      afterSettled: refreshTenants,
      busyMessage: "Installing credentials into the configured local dotenv file...",
      errorMessage: (error) => (error instanceof Error ? error.message : "Credential installation failed."),
      key: tenant.name,
      run: () =>
        fetchJson<TenantCredentialsResponse>(`/v1/tenants/${encodeURIComponent(tenant.name)}/credentials`, {
          body: JSON.stringify({ credentials }),
          headers: { "content-type": "application/json" },
          method: "POST"
        }),
      setMutations,
      successMessage: (payload) =>
        `Installed ${payload.installed_keys.length} credential key(s). Readiness: ${
          payload.tenant.credential_ready ? "ready" : "still missing required values"
        }. Refreshing status...`
    });

    if (payload?.ok) {
      setCredentialFormTenant(undefined);
    }
  }

  async function runLiveSyncAction(tenant: TenantStatus, action: TenantLiveAction) {
    const actionLabel = action === "start" ? "start" : action === "restart" ? "restart" : "stop";

    await runTrackedMutation<TenantLiveResponse>({
      afterSettled: refreshTenants,
      busyMessage: `Live sync ${actionLabel} requested. Waiting for the live-unit command to return...`,
      errorMessage: (error) => (error instanceof Error ? error.message : `Live sync ${actionLabel} failed.`),
      key: tenant.name,
      run: () =>
        fetchJson<TenantLiveResponse>(`/v1/tenants/${encodeURIComponent(tenant.name)}/live`, {
          body: JSON.stringify({ action }),
          headers: { "content-type": "application/json" },
          method: "POST"
        }),
      setMutations,
      successMessage: (payload) =>
        `Live sync ${payload.action || actionLabel} completed for ${payload.tenant.name}. Refreshing status...`
    });
  }

  async function startLiveSync(tenant: TenantStatus) {
    await runLiveSyncAction(tenant, "start");
  }

  async function restartLiveSync(tenant: TenantStatus) {
    await runLiveSyncAction(tenant, "restart");
  }

  async function stopLiveSync(tenant: TenantStatus) {
    setPendingStopTenant(undefined);
    await runLiveSyncAction(tenant, "stop");
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
            This React preview reads the existing tenant-status API and is migrating tenant setup, activation,
            live-sync controls, and backfill actions onto reusable operator-console primitives.
          </p>
        </div>
        <a className="button button--primary" href="/settings/tenants">
          Manage tenants
        </a>
      </div>

      <ConfirmDialog
        confirmLabel="Stop live sync"
        details="This stops the tenant's live-sync systemd user units. Mirrored history remains in the database."
        expectedText={pendingStopTenant?.name}
        message={
          pendingStopTenant
            ? `Stop live sync for ${pendingStopTenant.name}? Type the tenant name to confirm.`
            : "Stop live sync?"
        }
        onCancel={() => setPendingStopTenant(undefined)}
        onConfirm={() => {
          if (pendingStopTenant) {
            void stopLiveSync(pendingStopTenant);
          }
        }}
        open={Boolean(pendingStopTenant)}
        title="Stop live sync"
        tone="danger"
      />

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
              credentialFormOpen={credentialFormTenant === tenant.name}
              mutation={mutations[tenant.name]}
              onActivateTenant={activateTenant}
              onCancelCredentials={() => setCredentialFormTenant(undefined)}
              onInstallCredentials={installCredentials}
              onRequestCredentials={(tenantToEdit) => setCredentialFormTenant(tenantToEdit.name)}
              onRestartLiveSync={restartLiveSync}
              onRequestStopLiveSync={setPendingStopTenant}
              onRunInitialSync={runInitialSync}
              onStartLiveSync={startLiveSync}
              tenant={tenant}
            />
          ))}
        </div>
      ) : (
        <TenantStatusTable
          credentialFormTenant={credentialFormTenant}
          mutations={mutations}
          onActivateTenant={activateTenant}
          onCancelCredentials={() => setCredentialFormTenant(undefined)}
          onInstallCredentials={installCredentials}
          onRequestCredentials={(tenantToEdit) => setCredentialFormTenant(tenantToEdit.name)}
          onRestartLiveSync={restartLiveSync}
          onRequestStopLiveSync={setPendingStopTenant}
          onRunInitialSync={runInitialSync}
          onStartLiveSync={startLiveSync}
          tenants={state.tenants}
        />
      )}
    </section>
  );
}
