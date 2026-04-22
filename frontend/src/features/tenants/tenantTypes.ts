import type { StatusTone } from "../../contracts/status";

export type { StatusTone };

export interface TenantStatusBlock {
  label?: string;
  summary?: string;
  detail?: string;
  tone?: "ok" | "warn" | "bad" | "neutral" | string;
}

export interface TenantDbStats {
  channels?: number;
  messages?: number;
  files?: number;
  attachment_text?: number;
  ocr_text?: number;
  embedding_pending?: number;
  embedding_errors?: number;
  derived_pending?: number;
  derived_errors?: number;
}

export interface TenantSemanticProfile {
  name?: string;
  state?: string;
  tone?: "ok" | "warn" | "bad" | "neutral" | string;
  summary?: string;
  coverage?: {
    messages?: {
      ready?: number;
      total?: number;
    };
    derived_text_chunks?: {
      ready?: number;
      total?: number;
    };
  };
}

export interface TenantSemanticReadiness {
  summary?: string;
  profiles?: TenantSemanticProfile[];
}

export interface TenantStatus {
  name: string;
  domain?: string;
  enabled: boolean;
  db_synced: boolean;
  credential_ready: boolean;
  missing_required_credentials?: string[];
  validation_status?: string;
  live_units?: {
    webhooks?: string;
    daemon?: string;
  };
  db_stats?: TenantDbStats;
  sync_health?: TenantStatusBlock;
  backfill_status?: TenantStatusBlock;
  health?: TenantStatusBlock;
  semantic_readiness?: TenantSemanticReadiness;
  next_action?: string;
}

export interface TenantsResponse {
  ok: boolean;
  tenants: TenantStatus[];
}

export function toneFromApi(value: string | undefined): StatusTone {
  if (value === "ok") return "success";
  if (value === "warn") return "warning";
  if (value === "bad") return "danger";
  if (value === "info") return "info";
  return "neutral";
}
