---
name: slack-mirror-export
description: Export Slack Mirror conversations to HTML/JSON/PDF, including per-day channel exports, thread-aware formatting, attachment thumbnails/links, embedded PDF attachments, and semantic-hit daypack bundles. Use for requests like "export day/channel to PDF", "combine days into one PDF", and "generate one-shot search-term daypack".
---

# Slack Mirror Export

## Export scripts

- `scripts/export_channel_day.py` → channel/day HTML + JSON
- `scripts/export_channel_day_pdf.py` → single JSON to PDF
- `scripts/export_multi_day_pdf.py` → multiple JSONs to one PDF
- `scripts/export_semantic_daypack.py` → semantic terms -> day bundles -> combined PDF

## Useful flags

- `--embed-attachments`: render image attachments inline in PDF
- `--attach-files`: embed source files as PDF attachments (Acrobat-compatible)

## Current formatting behavior

- Human timestamps + user label resolution
- Thread reply visual treatment (indent + reply markers)
- Hyperlinked attachment entries
- Prominent clickable attachment links in PDF (`🔗` style)
- Speaker color-coded, bold datestamp/meta lines

## Recommended flow

1. Generate JSON with `export_channel_day.py`.
2. Render single PDF or combine multiple JSON exports.
3. For search-driven bundles, use `export_semantic_daypack.py`.
4. Report output paths + message count + attachment embedding mode.

## Caution

- PDF size can grow quickly with `--embed-attachments` and `--attach-files`.
- Prefer bounded channel/day scope when possible.
