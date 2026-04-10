# Installer Upgrade Path

State: OPEN
Roadmap: P01
Opened: 2026-04-09
Supersedes: `docs/dev/INSTALLER_UPGRADE_PLAN.md`

## Scope

Define the supported installer and upgrade path as a bounded product surface:

- fresh install
- upgrade
- validation
- rollback
- legacy unit migration

## Current State

- `slack-mirror user-env install|update|uninstall|status` exists
- compatibility script wrappers exist
- managed API launcher and API service unit exist
- remaining work is to tighten validation, rollback expectations, and operator-facing upgrade discipline

## Parallel Tracks

### Track A | Install And Upgrade Semantics

- fresh install steps
- upgrade sequencing
- config handling

### Track B | Validation And Rollback

- post-install validation
- duplicate-topology detection
- rollback rules

## Critical Path

- settle supported runtime topology
- then finalize install/upgrade and validation behavior against that topology

## Non-Goals

- packaging implementation details beyond install/upgrade semantics
- unrelated API or MCP contract work

## Acceptance Criteria

- one supported runtime topology is explicit
- fresh install and upgrade flows are explicit
- validation and rollback expectations are explicit
- legacy unit migration behavior is explicit

## Definition Of Done

This plan is done when install and upgrade behavior can be implemented or audited without consulting ad hoc notes, and the installer path is no longer spread across multiple conflicting docs.
