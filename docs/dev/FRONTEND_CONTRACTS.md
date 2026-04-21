# Frontend Contract Notes

This document records the first UI-facing contract boundary for the future
operator frontend. It complements:

- `docs/dev/plans/0051-2026-04-18-operator-frontend-reuse-architecture.md`
- `docs/dev/plans/0083-2026-04-21-cross-corpus-export-convergence.md`
- `docs/dev/plans/0096-2026-04-21-frontend-selected-result-contract-model.md`

## Selected Result Model

The selected-result UI model lives in:

```text
frontend/src/contracts/selectedResults.ts
```

The model is intentionally provider-neutral. Shared frontend code should talk
about sources, conversations, threads, participants, attachments, candidates,
targets, artifacts, and reports. Repo-local adapters map provider-specific API
fields into that shape.

## Slack To Neutral Mapping

| Slack Mirror field | Neutral frontend field |
| --- | --- |
| `workspace` / `workspace_id` | `SourceRef` |
| `channel_id` / `channel_name` | `ConversationRef` |
| `thread_ts` | `ThreadRef` |
| `ts` | `SelectedResultTarget.messageId` or `MessageContextItem.id` |
| `user_id` / `user_label` | `ParticipantRef` |
| `source_kind=file` / `source_id` | `AttachmentRef` |
| `action_target` | `SelectedResultTarget` |
| corpus result row | `SearchResultCandidate` |
| `context_policy` | `ContextPolicy` |
| `selected-results.json` | `SelectedResultReportArtifact` |

Provider-native identifiers should be preserved under `native` metadata instead
of becoming shared type names.

## Adapter Boundary

Shared or future shared code may own:

- result selection state
- visible-result bulk selection
- context-window controls
- managed artifact references
- selected-result report view actions
- status/type chips and print/copy affordances

Slack Mirror remains the owner of:

- API fetch paths
- auth/session handling
- Slack-specific route names and query parameters
- Slack native identifiers and fallback labels
- conversion from current API payloads into the neutral frontend contracts

## Extraction Gate

Do not move these types into a sibling shared package until at least one sibling
repo, most likely `../imcli`, can map its selected-result workflow into the same
shape without lossy provider assumptions.
