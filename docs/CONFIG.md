# Configuration (Preview)

`slack-mirror` uses YAML configuration with environment variable interpolation.

## Example

Copy `config.example.yaml` to `~/.config/slack-mirror/config.yaml` for a stable user-scope install, or to `config.local.yaml` in the repo for local dev/test.

```yaml
version: 1
storage:
  db_path: ${SLACK_MIRROR_DB:-~/.local/state/slack-mirror/slack_mirror.db}
  cache_root: ${SLACK_MIRROR_CACHE:-~/.local/cache/slack-mirror}
service:
  bind: ${SLACK_MIRROR_BIND:-127.0.0.1}
  port: ${SLACK_MIRROR_PORT:-8787}
  auth:
    enabled: ${SLACK_MIRROR_AUTH_ENABLED:-false}
    allow_registration: ${SLACK_MIRROR_AUTH_ALLOW_REGISTRATION:-false}
    registration_allowlist: ${SLACK_MIRROR_AUTH_REGISTRATION_ALLOWLIST:-}
    cookie_name: ${SLACK_MIRROR_AUTH_COOKIE_NAME:-slack_mirror_hosted_session}
    cookie_secure_mode: ${SLACK_MIRROR_AUTH_COOKIE_SECURE_MODE:-auto}
    session_days: ${SLACK_MIRROR_AUTH_SESSION_DAYS:-30}
    session_idle_timeout_seconds: ${SLACK_MIRROR_AUTH_SESSION_IDLE_TIMEOUT_SECONDS:-43200}
    login_attempt_window_seconds: ${SLACK_MIRROR_AUTH_LOGIN_WINDOW_SECONDS:-900}
    login_attempt_max_failures: ${SLACK_MIRROR_AUTH_LOGIN_MAX_FAILURES:-5}
exports:
  root_dir: ${SLACK_MIRROR_EXPORT_ROOT:-~/.local/share/slack-mirror/exports}
  local_base_url: ${SLACK_MIRROR_EXPORT_LOCAL_BASE_URL:-http://slack.localhost}
  external_base_url: ${SLACK_MIRROR_EXPORT_EXTERNAL_BASE_URL:-https://slack.ecochran.dyndns.org}
search:
  embeddings_model: ${SLACK_MIRROR_EMBED_MODEL:-text-embedding-3-large}
  keyword:
    weights:
      term: ${SLACK_MIRROR_SEARCH_KW_TERM_WEIGHT:-5.0}
      link: ${SLACK_MIRROR_SEARCH_KW_LINK_WEIGHT:-1.0}
      thread: ${SLACK_MIRROR_SEARCH_KW_THREAD_WEIGHT:-0.5}
      recency: ${SLACK_MIRROR_SEARCH_KW_RECENCY_WEIGHT:-2.0}
  semantic:
    mode_default: ${SLACK_MIRROR_SEARCH_MODE:-lexical}
    model: ${SLACK_MIRROR_SEARCH_SEM_MODEL:-local-hash-128}
    provider:
      type: ${SLACK_MIRROR_SEARCH_PROVIDER:-local_hash}
      command: ${SLACK_MIRROR_SEARCH_PROVIDER_COMMAND:-}
      url: ${SLACK_MIRROR_SEARCH_PROVIDER_URL:-}
      bearer_token_env: ${SLACK_MIRROR_SEARCH_PROVIDER_BEARER_ENV:-}
      timeout_s: ${SLACK_MIRROR_SEARCH_PROVIDER_TIMEOUT_S:-120}
      device: ${SLACK_MIRROR_SEARCH_PROVIDER_DEVICE:-}
      batch_size: ${SLACK_MIRROR_SEARCH_PROVIDER_BATCH_SIZE:-16}
      normalize_embeddings: ${SLACK_MIRROR_SEARCH_PROVIDER_NORMALIZE:-true}
      trust_remote_code: ${SLACK_MIRROR_SEARCH_PROVIDER_TRUST_REMOTE_CODE:-false}
      cache_folder: ${SLACK_MIRROR_SEARCH_PROVIDER_CACHE_FOLDER:-}
    weights:
      lexical: ${SLACK_MIRROR_SEARCH_LEXICAL_WEIGHT:-0.6}
      semantic: ${SLACK_MIRROR_SEARCH_SEMANTIC_WEIGHT:-0.4}
      semantic_scale: ${SLACK_MIRROR_SEARCH_SEMANTIC_SCALE:-10.0}
  rerank:
    provider:
      type: ${SLACK_MIRROR_RERANK_PROVIDER:-heuristic}
      model: ${SLACK_MIRROR_RERANK_MODEL:-BAAI/bge-reranker-v2-m3}
      device: ${SLACK_MIRROR_RERANK_DEVICE:-}
      batch_size: ${SLACK_MIRROR_RERANK_BATCH_SIZE:-16}
      trust_remote_code: ${SLACK_MIRROR_RERANK_TRUST_REMOTE_CODE:-false}
      cache_folder: ${SLACK_MIRROR_RERANK_CACHE_FOLDER:-}
  retrieval_profiles:
    baseline:
      mode: hybrid
      model: local-hash-128
      semantic_provider:
        type: local_hash
      rerank: false
    local-bge:
      mode: hybrid
      model: BAAI/bge-m3
      semantic_provider:
        type: sentence_transformers
        device: cuda
      rerank: false
      experimental: true
    local-bge-rerank:
      mode: hybrid
      model: BAAI/bge-m3
      semantic_provider:
        type: sentence_transformers
        device: cuda
      rerank: true
      rerank_provider:
        type: sentence_transformers
        model: BAAI/bge-reranker-v2-m3
        device: cuda
      experimental: true
    local-bge-http:
      mode: hybrid
      model: BAAI/bge-m3
      semantic_provider:
        type: http
        url: http://127.0.0.1:8791/
      rerank: false
      experimental: true
    local-bge-http-rerank:
      mode: hybrid
      model: BAAI/bge-m3
      semantic_provider:
        type: http
        url: http://127.0.0.1:8791/
      rerank: true
      rerank_provider:
        type: http
        url: http://127.0.0.1:8791/
        model: BAAI/bge-reranker-v2-m3
      experimental: true
  derived_text:
    provider:
      type: ${SLACK_MIRROR_DERIVED_TEXT_PROVIDER:-local_host_tools}
      command: ${SLACK_MIRROR_DERIVED_TEXT_COMMAND:-}
      url: ${SLACK_MIRROR_DERIVED_TEXT_URL:-}
      bearer_token_env: ${SLACK_MIRROR_DERIVED_TEXT_BEARER_ENV:-}
      timeout_s: ${SLACK_MIRROR_DERIVED_TEXT_TIMEOUT_S:-120}
      fallback_to_local: ${SLACK_MIRROR_DERIVED_TEXT_FALLBACK_TO_LOCAL:-true}

workspaces:
  - name: default
    team_id: ${SLACK_TEAM_ID:-}
    token: ${SLACK_TOKEN:-}
    outbound_token: ${SLACK_WRITE_BOT_TOKEN:-}
    user_token: ${SLACK_USER_TOKEN:-}
    outbound_user_token: ${SLACK_WRITE_USER_TOKEN:-}
    signing_secret: ${SLACK_SIGNING_SECRET:-}
    enabled: true
```

## Onboarding Model

This repo uses `workspace` as the canonical runtime term.
If you are thinking in hosted or customer-account terms, treat "tenant onboarding" here as "configure and activate one workspace entry under `workspaces:`".

For a first install, the canonical operator sequence lives in [docs/dev/USER_INSTALL.md](/home/ecochran76/workspace.local/slack-export/docs/dev/USER_INSTALL.md).

Configuration responsibilities break down like this:

- per-install:
  - `storage.*`
  - `service.*`
  - `exports.*`
- per-workspace:
  - one item under `workspaces:`
  - read-path credentials
  - write-path credentials
  - ingress credentials such as `signing_secret` when live event ingress is enabled

Minimum first-workspace checklist:

- one enabled workspace with a stable `name`
- explicit read credentials
- explicit write credentials
- `service.auth.enabled: true` if you want the browser surfaces
- `exports.local_base_url: http://slack.localhost` for local managed links

After editing config, the normal sequence is:

```bash
slack-mirror-user workspaces sync-config
slack-mirror-user workspaces verify --require-explicit-outbound
```

## Search provider settings

- `search.semantic.model` is the canonical selector for the message-semantic model.
- `search.semantic.provider` now controls how message embeddings are produced and queried.
- The shipped zero-dependency baseline remains:
  - `search.semantic.model: local-hash-128`
  - `search.semantic.provider.type: local_hash`
- The first stronger local path now available in-repo is:
  - `search.semantic.model: BAAI/bge-m3`
  - `search.semantic.provider.type: sentence_transformers`

Supported message-semantic provider types:

- `local_hash`
  - built-in baseline
  - no extra ML dependencies
- `sentence_transformers`
  - optional local in-process provider
  - intended for models such as `BAAI/bge-m3`
  - requires a compatible local install of `sentence-transformers` and `torch`
- `command`
  - external local helper process over stdin/stdout JSON
- `http`
  - external HTTP embedding service using the same request shape
  - can target the repo-owned loopback inference service (`slack-mirror search inference-serve`)

Example stronger local message-semantic config:

```yaml
search:
  semantic:
    model: BAAI/bge-m3
    provider:
      type: sentence_transformers
      device: cuda
      batch_size: 16
      normalize_embeddings: true
```

Notes:

- This stronger provider path currently applies to message embeddings and message-backed corpus search.
- Derived-text semantic retrieval now uses the same configured provider/model seam for query vectors.
- Persisted derived-text chunk embeddings are rolled out separately from messages and are tracked separately in readiness/health output.
- Heavy ML dependencies are intentionally optional so baseline installs and CI do not require `sentence-transformers`.
- The preferred heavy-model path is now the loopback-only local inference service, which keeps model objects warm in one process while CLI/API/MCP callers use HTTP-backed providers.
- The repo now exposes a readiness probe for this path:
  - `uv run slack-mirror search provider-probe --json`
  - add `--smoke` to force a tiny embed call after the dependency/runtime checks
- The repo-owned inference service can be run and probed with:
  - `uv run slack-mirror search inference-serve`
  - `uv run slack-mirror search inference-probe --smoke --model local-hash-128 --json`
- The optional dependency group for this local path is:
  - `uv sync --extra local-semantic`
- Message rollout and derived-text chunk rollout are intentionally separate:
  - messages: `uv run slack-mirror mirror embeddings-backfill ...`
  - derived-text chunks: `uv run slack-mirror mirror derived-text-embeddings-backfill ...`
- Reranking is currently an explicit opt-in search behavior:
  - message search: `slack-mirror search keyword ... --rerank`
  - corpus search: `slack-mirror search corpus ... --rerank`
  - current provider: `search.rerank.provider.type: heuristic`
  - learned local provider: `search.rerank.provider.type: sentence_transformers`
  - HTTP local-service provider: `search.rerank.provider.type: http`
  - probe before use: `slack-mirror search reranker-probe --smoke --json`

Example learned local reranker config:

```yaml
search:
  rerank:
    provider:
      type: sentence_transformers
      model: BAAI/bge-reranker-v2-m3
      device: cuda
      batch_size: 16
```

Example local inference service client config:

```yaml
search:
  inference:
    bind: 127.0.0.1
    port: 8791
    semantic_provider:
      type: sentence_transformers
      device: cuda
      batch_size: 16
      normalize_embeddings: true
    rerank_provider:
      type: sentence_transformers
      model: BAAI/bge-reranker-v2-m3
      device: cuda
      batch_size: 16
  semantic:
    model: BAAI/bge-m3
    provider:
      type: http
      url: http://127.0.0.1:8791/
      timeout_s: 120
  rerank:
    provider:
      type: http
      url: http://127.0.0.1:8791/
      timeout_s: 120
```

## Retrieval profiles

Retrieval profiles are named operator presets under `search.retrieval_profiles`. They bundle corpus-search mode, embedding model/provider, hybrid weights, and reranker intent without changing the global default search behavior.

The repo ships builtin profiles even if config does not define them:

- `baseline`
  - `local-hash-128`, `local_hash`, hybrid mode, no reranking
- `local-bge`
  - `BAAI/bge-m3`, `sentence_transformers`, hybrid mode, no reranking
- `local-bge-rerank`
  - `BAAI/bge-m3`, `sentence_transformers`, hybrid mode, experimental CrossEncoder reranking
- `local-bge-http`
  - `BAAI/bge-m3`, HTTP embedding provider against the local loopback inference service, hybrid mode, no reranking
- `local-bge-http-rerank`
  - `BAAI/bge-m3`, HTTP embedding provider plus HTTP reranker provider against the local loopback inference service, experimental CrossEncoder reranking

Use these commands to inspect and plan rollout:

```bash
slack-mirror search profiles
slack-mirror search semantic-readiness --workspace default --json
slack-mirror search corpus --workspace default --query "incident review" --retrieval-profile baseline
slack-mirror search corpus --workspace default --query "incident review" --mode hybrid --fusion rrf --explain
slack-mirror search scale-review --workspace default --profiles baseline --query "incident review" --repeats 2 --limit 5 --json
slack-mirror search benchmark-validate --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --json
slack-mirror mirror benchmark-embeddings-backfill --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --retrieval-profile local-bge-http --json
slack-mirror search profile-benchmark --workspace default --dataset docs/dev/benchmarks/slack_smoke.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --json
slack-mirror search profile-benchmark --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --fusion rrf --json
slack-mirror search benchmark-diagnose --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http,local-bge-http-rerank --json
slack-mirror search benchmark-query-variants --workspace default --dataset docs/dev/benchmarks/slack_live_relevance_noncontent.jsonl --profiles baseline,local-bge-http --variants original,lowercase,dehyphen,alnum --json
slack-mirror search provider-probe --retrieval-profile local-bge --json
slack-mirror search provider-probe --retrieval-profile local-bge-http --smoke --json
slack-mirror mirror rollout-plan --workspace default --retrieval-profile local-bge --limit 500 --json
```

`search semantic-readiness` is read-only and returns profile states for one workspace or all enabled workspaces. `mirror rollout-plan` is read-only. It reports current message and derived-text chunk embedding coverage for the profile model and emits bounded commands for provider probing, message embedding backfill, derived-text chunk embedding backfill, optional reranker probing, and search-health verification.

`search scale-review` is read-only and defaults to the release-safe `baseline` profile. Use it before changing index or inference architecture; it reports corpus counts, embedding coverage, repeated query latency by retrieval profile, and a machine-readable decision recommending whether to stay SQLite/exact, evaluate a SQLite-native vector extension, or evaluate a local ANN service.

`search benchmark-validate` is read-only and checks benchmark dataset labels against the configured workspace DB. It reports unresolved labels, ambiguous labels, and per-profile configured-model coverage so partial rollout does not get confused with model-quality evidence.

`mirror benchmark-embeddings-backfill` is a bounded write command for covering only the targets referenced by benchmark labels under a selected retrieval profile. Use it when benchmark validation shows label coverage is missing and broad tenant rollout is not justified.

`search profile-benchmark` is read-only and compares multiple retrieval profiles against the same JSONL benchmark dataset. Its default output is aggregate-only; use `--include-details` only when per-query rows are safe to inspect locally. For corpus benchmarks, `--fusion weighted` is the release-default path and `--fusion rrf` evaluates reciprocal-rank fusion without changing tenant defaults.

`search benchmark-diagnose` is read-only and compares per-query target ranks across retrieval profiles. Default output is non-content: stable labels, ranks, profile movement, source counts, and compact explain metadata. Use `--fusion rrf` to diagnose reciprocal-rank fusion, and use `--include-text` only for local debugging when message bodies or snippets are safe to inspect.

`search benchmark-query-variants` is read-only and compares deterministic query formulations across retrieval profiles. Builtin variants are `original`, `lowercase`, `dehyphen`, and `alnum`; `dataset` and `dataset:<key>` consume authored row-level `query_variants` values when present. Default output is aggregate-only and non-content; use `--include-details` to inspect per-query stable result labels locally.

The same readiness payload is exposed to API and MCP clients:

- `GET /v1/search/profiles`
- `GET /v1/search/semantic-readiness`
- `GET /v1/workspaces/<workspace>/search/semantic-readiness`
- MCP `search.profiles`
- MCP `search.semantic_readiness`

Do not use `local-bge-rerank` as the release default yet. The learned reranker is available for bounded experiments, but live rehearsal has not shown enough stable relevance lift to justify default rollout.

Release policy for the first stable MCP-capable user-scoped install:

- keep `baseline` as the default installed retrieval profile
- treat `local-bge` as a supported opt-in profile that requires provider probe, rollout plan, bounded backfill, semantic readiness, and search health checks before tenant promotion
- keep `local-bge-rerank` experimental
- keep SQLite as canonical storage
- evaluate a SQLite-native vector extension before any vector DB or ANN service if latency remains above target
- sideline DuckDB for this release path; it may be revisited later as an analytics, reporting, or search-sidecar experiment, not as canonical storage

## Corpus Fusion And Explainability

Corpus hybrid search supports explicit fusion policies:

- `weighted`
  - default release-safe behavior
  - combines lexical score plus scaled semantic score using `search.semantic.weights`
- `rrf`
  - opt-in reciprocal-rank fusion
  - combines lexical and semantic candidate ranks while preserving deterministic ordering

Use CLI `--fusion weighted|rrf`, API query parameter `fusion=weighted|rrf`, or MCP `search.corpus` argument `fusion`. Results include `_explain` metadata with mode, source, fusion method, lane scores, lane ranks, weights, and rerank provider when applicable.

Corpus result rows also include `action_target` metadata for stable selection. Use `action_target` when moving search hits into export, report, or action workflows instead of parsing `source_label`, snippets, or display text.

Provider field semantics:

- `type`
  - provider implementation to use
- `command`
  - executable for `command` provider mode
- `url`
  - endpoint base URL for `http` provider mode
- `bearer_token_env`
  - environment-variable name holding the bearer token for `http`
- `timeout_s`
  - request timeout for `command` and `http` providers
- `device`
  - optional `sentence_transformers` device, for example `cuda` or `cpu`
- `batch_size`
  - optional `sentence_transformers` batch size
- `normalize_embeddings`
  - whether to request normalized embeddings from the provider
- `trust_remote_code`
  - forwarded to `SentenceTransformer(...)` for model-loading edge cases
- `cache_folder`
  - optional model cache override for `sentence_transformers`

Use `slack-mirror-user` after `user-env install`; it pins the managed config, DB, and cache paths. Use `uv run slack-mirror ...` from the repo before the managed wrapper exists.

For staged tenant onboarding, keep a new workspace entry at `enabled: false` until its credentials are present. Default `workspaces verify` skips disabled scaffolds; use `workspaces verify --workspace <name>` when you want to confirm that a staged entry is still disabled before activation.
For Slack app creation, credential collection, and the app-manifest location, see [docs/SLACK_MANIFEST.md](/home/ecochran76/workspace.local/slack-export/docs/SLACK_MANIFEST.md).

## Interpolation syntax

- `${VAR}` → required env var (empty if not set)
- `${VAR:-fallback}` → env var with default fallback

## Token selection by action

- `token` / `user_token` are the default read-path credentials.
- `outbound_token` / `outbound_user_token` are used for write actions such as sending messages or thread replies.
- `app_token` is the Socket Mode app-level token (`xapp-...`) used by `mirror serve-socket-mode`.
- If outbound token fields are not set, the service falls back to workspace-aware env aliases for writes.
- For the `default` workspace, generic env names like `SLACK_BOT_TOKEN` and `SLACK_USER_TOKEN` are considered write-capable fallbacks.
- For production installs, prefer explicit outbound fields rather than fallback heuristics.
- `workspaces verify --require-explicit-outbound` enforces that policy during validation.
- `signing_secret` is the ingress-path credential used to validate incoming Slack requests for live event delivery.

## Path resolution rules

- `dotenv`, `storage.db_path`, and `storage.cache_root` are resolved relative to the **config file directory**, not the process cwd.
- environment interpolation on `dotenv` is resolved before the dotenv file is loaded, so paths like `${SLACK_MIRROR_DOTENV:-~/credentials/API-keys.env}` behave as expected.
- `~` is expanded for user-scope paths.
- If `--config` is omitted, the CLI searches in this order:
  1. `./config.local.yaml`
  2. `./config.yaml`
  3. `~/.config/slack-mirror/config.yaml`

For automation, prefer passing an explicit `--config` path anyway.

## Search and extraction settings

- `search.keyword.weights.*` tunes the lexical scorer.
- `search.semantic.weights.*` tunes hybrid lexical-vs-semantic fusion for message and corpus search.
- `search corpus --fusion` chooses the corpus hybrid fusion algorithm for a request. `weighted` is the default; `rrf` is opt-in.
- `search.derived_text.provider.*` controls attachment and OCR extraction providers separately from message embeddings.
- `search.rerank.provider.type` selects the reranker provider for explicit `--rerank` searches. The shipped baseline supports `heuristic` and `none`; optional learned local reranking uses `sentence_transformers`.
- `search.rerank.provider.model`, `device`, `batch_size`, `trust_remote_code`, and `cache_folder` configure the optional `sentence_transformers` CrossEncoder reranker. This path is still opt-in and should be probed before live use.
- `search.embeddings_model` remains as a legacy field from earlier hosted-embedding work and is no longer the primary selector for the local message-semantic path; prefer `search.semantic.model`.
- `search readiness` and `search health` now report configured-model coverage separately for:
  - message embeddings
  - `attachment_text` chunk embeddings
  - `ocr_text` chunk embeddings

## Service and export settings

- `service.bind` and `service.port` are the canonical local API listen settings.
- `slack-mirror api serve` now defaults to those config values when `--bind` or `--port` are omitted.
- `service.auth.enabled` turns on the local browser-auth baseline for published runtime-report and export surfaces.
- `service.auth.allow_registration` controls whether new local frontend users can self-register through `/register`. The shipped config template now defaults this to `false` for a stricter live posture.
- `service.auth.registration_allowlist` optionally restricts self-registration to specific normalized usernames, including email-style usernames such as `ecochran76@gmail.com`.
- when `service.auth.allow_registration` remains `false`, use `slack-mirror user-env provision-frontend-user --username <identity>` for first-user bootstrap instead of temporarily reopening browser self-registration.
- `service.auth.cookie_name`, `service.auth.cookie_secure_mode`, and `service.auth.session_days` control the browser session cookie contract.
- `service.auth.session_idle_timeout_seconds` controls inactivity expiry for browser sessions based on `last_seen_at`.
- `service.auth.login_attempt_window_seconds` and `service.auth.login_attempt_max_failures` control the bounded failed-login throttle for `/auth/login`.
- `service.auth.cookie_secure_mode` accepts:
  - `auto` — mark cookies `Secure` only for HTTPS requests
  - `always` — always mark cookies `Secure`
  - `never` — never mark cookies `Secure`
- in `auto`, the service first trusts browser origin/referrer scheme, then reverse-proxy proto headers, and finally falls back to the configured local/external base-host mapping when deciding whether a request is HTTPS-backed.
- the older `service.auth.cookie_secure` boolean is still accepted as a compatibility override, but `cookie_secure_mode` is the canonical setting.
- when frontend auth is enabled, browser auth POST routes (`/auth/register`, `/auth/login`, `/auth/logout`) are same-origin only and require a matching `Origin` or `Referer` header.
- when the failed-login threshold is exceeded inside the configured window, `/auth/login` returns `429 RATE_LIMITED` with retry metadata instead of a generic invalid-credential response.
- when a browser session exceeds the configured inactivity timeout, the shared auth resolver revokes it and treats it as unauthenticated on the next request.
- per-user browser session inspection and revocation are available through `/auth/sessions` and `/auth/sessions/<id>/revoke`.
- when frontend auth is enabled, protected HTML routes redirect unauthenticated browsers to `/login`, while protected JSON routes fail with `AUTH_REQUIRED`.
- `exports.root_dir` is the user-scoped bundle root for managed export artifacts.
- `exports.local_base_url` is the preferred base URL for local reverse-proxied download links, intended for `http://slack.localhost`.
- `exports.external_base_url` is the preferred base URL for externally published download links, intended for `https://slack.ecochran.dyndns.org`.
- managed exports now emit both local and external URL maps when both base URLs are configured, so consumers can switch audiences without rerunning the export.
- the API export manifest endpoints rebuild bundle URLs from current config, so the live service remains the canonical owner of the published HTTP/HTTPS export contract.

Managed export URLs use this path contract:

- `/exports/<export-id>` serves the bundle HTML report
- `/exports/<export-id>/<filepath>`
- `/exports/<export-id>/<filepath>/preview`
- `/v1/exports`
- `/v1/exports/<export-id>`
- `/auth/status`
- `/auth/session`
- `/auth/sessions`
- `/auth/register`
- `/auth/login`
- `/auth/logout`
- `/login`
- `/register`

Current preview support behind the local API:
- images: inline preview
- PDFs: iframe preview
- `.docx`: HTML preview through `mammoth`
- `.pptx`: slide-by-slide HTML summary through the repo's OOXML extraction path
- `.xlsx`: sheet-table HTML summary through the repo's OOXML extraction path
- `.odt`: HTML text summary through the repo's OpenDocument extraction path
- `.odp`: slide-by-slide HTML summary through the repo's OpenDocument extraction path
- `.ods`: sheet-table HTML summary through the repo's OpenDocument extraction path
- text-like files (`text/*`, JSON, XML): escaped text preview
- other content types: `PREVIEW_UNSUPPORTED`

`<export-id>` is deterministic, URL-friendly, and human-readable. The current format is a bounded readable slug with a short stable hash suffix, for example:

- `channel-day-default-general-2026-04-12-a1b2c3d4e5`

## Commands (scaffold)

```bash
python -m slack_mirror.cli.main --config config.yaml mirror init
python -m slack_mirror.cli.main --config config.yaml workspaces sync-config
python -m slack_mirror.cli.main --config config.yaml workspaces verify
python -m slack_mirror.cli.main --config config.yaml workspaces verify --require-explicit-outbound
python -m slack_mirror.cli.main --config config.yaml workspaces list
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-messages --channel-limit 5
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-messages --oldest 1700000000.000000 --latest 1800000000.000000
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --cache-root ./cache
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --file-types all --cache-root ./cache
python -m slack_mirror.cli.main --config config.yaml mirror backfill --workspace default --include-files --download-content --cache-root ./cache
python -m slack_mirror.cli.main channels sync-from-tool
python -m slack_mirror.cli.main search reindex-keyword --workspace default
python -m slack_mirror.cli.main search keyword --workspace default --query deploy --limit 20
python -m slack_mirror.cli.main search keyword --workspace default --query "deploy from:<@U123> channel:<#C123> has:link -draft after:1700000000"
python -m slack_mirror.cli.main docs generate --format markdown --output docs/CLI.md
python -m slack_mirror.cli.main docs generate --format man --output docs/slack-mirror.1
python scripts/check_generated_docs.py

# after install (entrypoint)
slack-mirror --config config.yaml mirror init

# webhook service
python -m slack_mirror.cli.main --config config.yaml mirror serve-webhooks --workspace default --bind 127.0.0.1 --port 8787
python -m slack_mirror.cli.main --config config.yaml mirror process-events --workspace default --limit 200
python -m slack_mirror.cli.main --config config.yaml mirror process-events --workspace default --loop --interval 2 --max-cycles 10

# shell completion scripts
python -m slack_mirror.cli.main completion print bash > /tmp/slack-mirror.bash
python -m slack_mirror.cli.main completion print zsh > /tmp/_slack-mirror
```

> Note: This is scaffold-level documentation during Phase A. Behavior and command names may evolve.
