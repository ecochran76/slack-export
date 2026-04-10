# Slack Mirror Architecture

This project is evolving from a one-time Slack export script into a local Slack service platform.

The target is not "more scripts." The target is one application core with multiple thin surfaces.

## Goals

- mirror one or more Slack workspaces locally
- keep data fresh through live ingest plus reconciliation
- provide keyword and semantic search over one canonical corpus
- expose the platform through CLI, API, and MCP
- support outbound messaging, replies, and triggerable listener workflows
- run as one supported long-lived service topology per install

## Architectural Direction

The canonical system should look like this:

1. **Application Core**
   - owns workspace routing, sync state, event processing, search, embeddings, outbound messaging, and hook dispatch

2. **Canonical Data Layer**
   - one SQLite database
   - one cache root
   - one message/event/job model

3. **Service Runtime**
   - one supported supervisor-managed runtime topology
   - one live ingress path
   - one worker/control loop

4. **Thin Surfaces**
   - CLI
   - local API
   - MCP server
   - agent skills

## Core Components

### 1. Sync and Reconcile

- Slack Web API backfill
- live ingest from Socket Mode or webhook-compatible ingress
- replay-safe event processing
- reconcile path for missed or delayed updates

### 2. Canonical Persistence

- multi-workspace SQLite schema
- queue tables for events and derived work
- FTS and embedding storage
- deterministic local cache paths

### 3. Search and Retrieval

- FTS keyword search
- semantic retrieval
- shared ranking and query interpretation
- freshness and backlog observability

### 4. Outbound Messaging

- send message
- send thread reply
- shared audit logging, retry, and idempotency behavior

### 5. Hooks and Listeners

- subscription model for local consumers
- listener dispatch on selected service events
- delivery logging and replay-aware semantics

The shipped listener registration, delivery, and acknowledgement semantics are part of the shared transport contract. See [API_MCP_CONTRACT.md](/home/ecochran76/workspace.local/slack-export/docs/API_MCP_CONTRACT.md).

### 6. API and MCP

- local API for programmatic use
- MCP server backed by the same application service layer
- shared contracts rather than duplicate logic
- shared machine-readable success and error envelopes for transport callers

See [API_MCP_CONTRACT.md](/home/ecochran76/workspace.local/slack-export/docs/API_MCP_CONTRACT.md) for the current shipped transport contract.

## Runtime Model

The supported runtime topology is:

- one ingress service per workspace
- one unified daemon per workspace

Do not run split event and embedding workers alongside the unified daemon for the same workspace. Duplicate writers against the same SQLite database are not a supported architecture.

## Multi-Workspace Model

All primary entities are keyed by `workspace_id` in addition to Slack identifiers:

- users
- channels
- messages
- files
- canvases
- events
- sync checkpoints
- derived jobs

One install should be able to manage multiple workspaces without creating parallel shadow databases.

## Ownership Rules

- `slack_mirror.core` owns schema, persistence, and canonical data behavior.
- `slack_mirror.sync` owns Slack ingest and reconcile mechanics.
- `slack_mirror.service` owns runtime behavior, queue execution, and listener dispatch.
- `slack_mirror.cli` is an operator surface, not the business-logic owner.
- future API and MCP layers must call shared application logic rather than re-implement behavior.

## Security and Secrets

- config-driven workspace scoping
- environment-variable interpolation for secrets
- clear separation between durable mirror data and auth/session secrets
- outbound actions must use the same workspace/auth routing discipline as inbound sync

## Near-Term Architectural Priorities

1. consolidate on one supported runtime/install model
2. define installer and release discipline
3. define the application service boundary for API and MCP
4. add first-class outbound messaging
5. add listener and hook contracts
6. move agent skills onto stable service contracts

For sequencing and execution detail, see [ROADMAP.md](/home/ecochran76/workspace.local/slack-export/ROADMAP.md), [RUNBOOK.md](/home/ecochran76/workspace.local/slack-export/RUNBOOK.md), and the active plans under [docs/dev/plans](/home/ecochran76/workspace.local/slack-export/docs/dev/plans).
