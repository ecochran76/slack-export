#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _compact_dict(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _default_schema_dir() -> Path:
    workspace_root = Path(__file__).resolve().parents[2]
    return workspace_root / "ragmail-storage-architecture" / "schemas" / "communications"


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _schema_store(schema_dir: Path) -> dict[str, Any]:
    store: dict[str, Any] = {}
    for path in schema_dir.glob("*.schema.json"):
        payload = _load_json(path)
        store[path.name] = payload
        schema_id = payload.get("$id")
        if isinstance(schema_id, str):
            store[schema_id] = payload
    return store


def _target_kind(native_kind: Any) -> str:
    kind = str(native_kind or "").strip()
    if kind == "message":
        return "slack_message"
    if kind == "derived_text":
        return "derived_text"
    return "event"


def map_action_target(target: dict[str, Any]) -> dict[str, Any]:
    native_kind = str(target.get("kind") or "").strip()
    target_kind = _target_kind(native_kind)
    hit_kind = "chunk" if native_kind == "derived_text" and target.get("chunk_index") is not None else target_kind
    service_ids = _compact_dict(
        {
            "message_id": target.get("ts"),
            "thread_id": target.get("thread_ts"),
            "conversation_id": target.get("channel_id"),
            "channel_id": target.get("channel_id"),
            "workspace_id": target.get("workspace"),
            "derived_text_id": target.get("derived_text_id"),
        }
    )
    native_ids = _compact_dict(
        {
            "workspace": target.get("workspace"),
            "channel_id": target.get("channel_id"),
            "ts": target.get("ts"),
            "thread_ts": target.get("thread_ts"),
            "source_kind": target.get("source_kind"),
            "source_id": target.get("source_id"),
            "derivation_kind": target.get("derivation_kind"),
            "extractor": target.get("extractor"),
            "chunk_index": target.get("chunk_index"),
            "id": target.get("id"),
        }
    )
    return _compact_dict(
        {
            "schema_version": 1,
            "target_kind": target_kind,
            "hit_kind": hit_kind,
            "tenant": target.get("workspace"),
            "namespace": target.get("workspace"),
            "platform": "slack",
            "selection_label": target.get("selection_label") or target.get("id"),
            "service_ids": service_ids or None,
            "native_ids": native_ids or None,
            "source_refs": native_ids or None,
            "extensions": {"slack_action_target": target},
        }
    )


def _map_context_policy(policy: dict[str, Any]) -> dict[str, Any]:
    return _compact_dict(
        {
            "schema_version": 1,
            "before_count": policy.get("before"),
            "after_count": policy.get("after"),
            "include_text": policy.get("include_text"),
            "max_text_chars": policy.get("max_text_chars"),
            "boundary": "same_channel",
            "extensions": {"slack_context_policy": policy},
        }
    )


def _map_participant(participant: dict[str, Any]) -> dict[str, Any]:
    native = participant.get("native") if isinstance(participant.get("native"), dict) else {}
    return _compact_dict(
        {
            "role": participant.get("role") or "participant",
            "display_name": participant.get("display_name"),
            "service_participant_id": participant.get("id") or native.get("user_id"),
            "source_refs": native or None,
            "extensions": {"slack_participant": participant},
        }
    )


def _map_thread(thread: Any) -> dict[str, Any] | None:
    if not isinstance(thread, dict):
        return None
    native = thread.get("native") if isinstance(thread.get("native"), dict) else {}
    thread_id = thread.get("id") or thread.get("root_ts") or native.get("thread_ts") or native.get("ts")
    return _compact_dict(
        {
            "id": str(thread_id) if thread_id is not None else None,
            "type": "thread" if thread_id else "provider_defined",
            "source_refs": _compact_dict(
                {
                    "thread_ts": thread.get("root_ts") or native.get("thread_ts"),
                    "ts": native.get("ts"),
                }
            ),
            "extensions": {"slack_thread": thread},
        }
    )


def _map_attachment(attachment: dict[str, Any], *, selected: bool) -> dict[str, Any]:
    native = attachment.get("native") if isinstance(attachment.get("native"), dict) else {}
    return _compact_dict(
        {
            "id": str(attachment.get("id") or native.get("file_id") or "unknown"),
            "filename": attachment.get("filename"),
            "media_type": attachment.get("media_type"),
            "selected": bool(selected),
            "source_refs": native or None,
            "extensions": {"slack_attachment": attachment},
        }
    )


def _map_derived_text_ref(ref: dict[str, Any]) -> dict[str, Any]:
    ref_id = "|".join(
        str(part)
        for part in [
            ref.get("source_kind"),
            ref.get("source_id"),
            ref.get("derivation_kind"),
            ref.get("extractor"),
            ref.get("chunk_index"),
        ]
        if part is not None
    )
    return _compact_dict(
        {
            "id": ref_id or "derived-text",
            "source_kind": ref.get("source_kind"),
            "source_id": ref.get("source_id"),
            "derivation_kind": ref.get("derivation_kind"),
            "extractor": ref.get("extractor"),
            "chunk_index": ref.get("chunk_index"),
            "start_offset": ref.get("start_offset"),
            "end_offset": ref.get("end_offset"),
            "text": ref.get("text"),
            "media_type": ref.get("media_type"),
            "confidence": ref.get("confidence"),
            "source_refs": _compact_dict(
                {
                    "source_label": ref.get("source_label"),
                    "language_code": ref.get("language_code"),
                }
            ),
            "extensions": {"slack_derived_text_ref": ref},
        }
    )


def _map_source_refs(refs: dict[str, Any]) -> dict[str, Any]:
    mapped = dict(refs)
    for key in ["workspace_id", "channel_id", "ts", "service_message_id", "service_thread_id", "service_account_id"]:
        if mapped.get(key) is not None:
            mapped[key] = str(mapped[key])
    return mapped


def map_event(event: dict[str, Any]) -> dict[str, Any]:
    native_kind = str(event.get("kind") or "").strip()
    kind = "derived_text" if native_kind == "derived_text_chunk" else "slack_message" if native_kind == "message" else "system_event"
    native_source_refs = event.get("source_refs") if isinstance(event.get("source_refs"), dict) else {}
    source_refs = _map_source_refs(native_source_refs)
    warnings = event.get("warnings") if isinstance(event.get("warnings"), list) else []
    action_target = event.get("action_target") if isinstance(event.get("action_target"), dict) else {}
    return _compact_dict(
        {
            "schema_version": 1,
            "id": str(event.get("id") or ""),
            "kind": kind,
            "relation": event.get("relation"),
            "exact_hit": bool(event.get("exact_hit")),
            "action_target": map_action_target(action_target) if action_target else None,
            "tenant": source_refs.get("workspace") or event.get("tenant"),
            "namespace": source_refs.get("workspace") or event.get("namespace"),
            "platform": event.get("platform") or "slack",
            "subject": event.get("subject"),
            "text": event.get("text"),
            "timestamp": event.get("timestamp"),
            "participants": [
                _map_participant(participant)
                for participant in event.get("participants", [])
                if isinstance(participant, dict)
            ],
            "thread": _map_thread(event.get("thread")),
            "source_refs": source_refs,
            "attachments": [
                _map_attachment(attachment, selected=bool(event.get("selected") or event.get("exact_hit")))
                for attachment in event.get("attachments", [])
                if isinstance(attachment, dict)
            ],
            "derived_text_refs": [
                _map_derived_text_ref(ref)
                for ref in event.get("derived_text_refs", [])
                if isinstance(ref, dict)
            ],
            "compatibility_warnings": warnings,
            "extensions": {"slack_event": event},
        }
    )


def map_selected_results_payload(payload: dict[str, Any]) -> dict[str, Any]:
    context_pack = payload.get("context_pack") if isinstance(payload.get("context_pack"), dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    targets = source.get("targets") if isinstance(source.get("targets"), list) else []
    unresolved = context_pack.get("unresolved") if isinstance(context_pack.get("unresolved"), list) else []
    context_policy = context_pack.get("context_policy") if isinstance(context_pack.get("context_policy"), dict) else {}
    return _compact_dict(
        {
            "schema_version": 1,
            "kind": "selected_result_export",
            "export_id": str(payload.get("export_id") or ""),
            "title": payload.get("title"),
            "created_at": payload.get("generated_at"),
            "producer": {"name": "slack-mirror", "repo": "slack-export"},
            "tenant": payload.get("workspace"),
            "namespace": payload.get("workspace"),
            "selected_targets": [map_action_target(target) for target in targets if isinstance(target, dict)],
            "context_policy": _map_context_policy(context_policy),
            "events": [map_event(event) for event in payload.get("events", []) if isinstance(event, dict)],
            "unresolved_targets": [
                {
                    "target": map_action_target(entry.get("target", {})),
                    "reason": str(entry.get("reason") or "unresolved"),
                    "index": entry.get("index"),
                    "extensions": {"slack_unresolved": entry},
                }
                for entry in unresolved
                if isinstance(entry, dict) and isinstance(entry.get("target"), dict)
            ],
            "native_payload_refs": {"selected_results_json": "selected-results.json"},
            "extensions": {"slack_selected_results": payload},
        }
    )


def validate_contract(payload: dict[str, Any], schema_dir: Path) -> list[str]:
    try:
        from jsonschema import Draft202012Validator
        from referencing import Registry, Resource
        from referencing.jsonschema import DRAFT202012
    except ModuleNotFoundError as exc:
        raise SystemExit(
            "Missing jsonschema. Run with: uv run --isolated --with jsonschema "
            "python scripts/validate_selected_results_communications_contract.py --input <selected-results.json>"
        ) from exc

    schema = _load_json(schema_dir / "selected-result-export.schema.json")
    store = _schema_store(schema_dir)
    resources = [
        (schema_id, Resource.from_contents(schema_payload, default_specification=DRAFT202012))
        for schema_id, schema_payload in store.items()
        if schema_id.startswith("https://")
    ]
    registry = Registry().with_resources(resources)
    for schema_payload in store.values():
        Draft202012Validator.check_schema(schema_payload)
    validator = Draft202012Validator(schema, registry=registry)
    return [
        f"{'/'.join(str(part) for part in error.absolute_path) or '<root>'}: {error.message}"
        for error in sorted(validator.iter_errors(payload), key=lambda item: list(item.path))
    ]


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Map Slack selected-results.json to the draft communications contract and validate it."
    )
    parser.add_argument("--input", type=Path, required=True, help="Slack selected-results.json artifact.")
    parser.add_argument("--schema-dir", type=Path, default=_default_schema_dir(), help="Draft communications schema directory.")
    parser.add_argument("--output", type=Path, help="Optional path for the mapped provider-neutral JSON.")
    parser.add_argument("--no-validate", action="store_true", help="Only write the mapped JSON; skip jsonschema validation.")
    args = parser.parse_args()

    mapped = map_selected_results_payload(_load_json(args.input))
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(mapped, indent=2, sort_keys=True), encoding="utf-8")

    if args.no_validate:
        print(f"WROTE {args.output}" if args.output else "MAPPED")
        return 0

    errors = validate_contract(mapped, args.schema_dir)
    if errors:
        print(f"FAIL {args.input}")
        for error in errors:
            print(f"  {error}")
        return 1
    print(f"PASS {args.input}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
