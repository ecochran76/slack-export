# Export Workflows (HTML/JSON/PDF)

This doc covers the current export scripts for channel/day and semantic-hit day packs.

## 1) Single channel/day export

Generate HTML + JSON from mirrored DB:

```bash
python scripts/export_channel_day.py \
  --db ./.local/state/slack_mirror_test.db \
  --workspace soylei \
  --channel general-business-4 \
  --day 2022-06-10 \
  --tz America/Chicago \
  --out-html exports/soylei-general-business-4-2022-06-10.html \
  --out-json exports/soylei-general-business-4-2022-06-10.json
```

Features:
- includes thread replies for threads rooted on that day
- user ID -> readable display labels
- human-readable timestamps
- HTML thread styling (reply badge + connector line)
- HTML attachment hyperlinks + image thumbnails (3.5in wide)

## 2) Render JSON export to PDF

```bash
.venv/bin/python scripts/export_channel_day_pdf.py \
  --input-json exports/soylei-general-business-4-2022-06-10.json \
  --output-pdf exports/soylei-general-business-4-2022-06-10.pdf \
  --embed-attachments \
  --attach-files
```

Flags:
- `--embed-attachments`: inline image rendering in PDF
- `--attach-files`: embed source files as PDF file attachments (Acrobat-compatible)

PDF UX:
- thread-reply labeling/indentation
- bold, color-coded datestamp lines by speaker
- prominent clickable attachment links (`🔗 open: ...`)

## 3) Combine multiple channel/day JSON exports into one PDF

```bash
.venv/bin/python scripts/export_multi_day_pdf.py \
  --inputs exports/hit-days/*.json \
  --output exports/soylei-semantic-hits-daypack.pdf \
  --embed-attachments \
  --attach-files
```

## 4) One-shot semantic search -> full-day exports -> combined PDF

```bash
python scripts/export_semantic_daypack.py \
  --workspace soylei \
  --terms "asphalt emulsions" "pure asphalt" "hawkseale" \
  --output-pdf exports/soylei-semantic-hits-daypack-auto.pdf \
  --embed-attachments \
  --attach-files
```

Pipeline:
1. semantic/hybrid searches per term
2. collect channel/day bundles from hits
3. export each bundle via `export_channel_day.py`
4. combine via `export_multi_day_pdf.py`
