# Export Workflows (HTML/JSON/PDF/DOCX)

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

## 2) Render JSON export to DOCX

```bash
python scripts/export_channel_day_docx.py \
  --input-json exports/soylei-general-business-4-2022-06-10.json \
  --output-docx exports/soylei-general-business-4-2022-06-10.docx
```

Style flags:
- `--font-family Aptos`
- `--font-size-pt 11`
- `--margin-in 1.25`
- `--compactness cozy`
- `--accent-color 8B5CF6`

DOCX UX in the current baseline:
- single channel/day JSON is the canonical input artifact
- compact letter-page layout with 1in margins
- sans-serif 10pt body text by default
- thread-reply labeling and indentation
- speaker/timestamp metadata lines
- clickable attachment links for local files or permalinks
- explicit paragraph styles for metadata, message body, reply body, and attachment blocks
- human-readable attachment metadata like `PDF document` or `Word document` instead of raw MIME strings
- attachment follow-up lines that distinguish local-only files from permalink-backed files
- no second SQLite-querying DOCX path
- package output is now compatible with the local LibreOffice render/QA path used by `docx-skill`
- bounded appearance configuration is now supported for:
  - font family
  - body font size
  - page margins
  - compact vs cozy spacing
  - accent color
- current canonical fixture profiles for visual review are:
  - `compact_default`: `Arial`, `10pt`, `1.0in`, `compact`, `#3B5B7A`
  - `cozy_review`: `Aptos`, `11pt`, `1.25in`, `cozy`, `#8B5CF6`

Review-artifact generation:

```bash
python scripts/render_export_docx_fixtures.py --output-dir exports/docx-fixtures
```

This produces a stable review bundle with:
- canonical sample JSON inputs
- rendered single-day and multi-day DOCX outputs for `compact_default` and `cozy_review`
- structural validation summaries in `manifest.json`
- rendered PDF/PNG review artifacts through the local `docx-skill` path when available

## 3) Render JSON export to PDF

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

## 4) Combine multiple channel/day JSON exports into one PDF

```bash
.venv/bin/python scripts/export_multi_day_pdf.py \
  --inputs exports/hit-days/*.json \
  --output exports/soylei-semantic-hits-daypack.pdf \
  --embed-attachments \
  --attach-files
```

## 5) Combine multiple channel/day JSON exports into one DOCX

```bash
.venv/bin/python scripts/export_multi_day_docx.py \
  --inputs exports/hit-days/*.json \
  --output-docx exports/soylei-semantic-hits-daypack.docx \
  --title "Slack Export DOCX Package"
```

DOCX UX in the current multi-day baseline:
- builds from the same channel/day JSON artifact as the single-day DOCX renderer
- inserts page breaks between bundled day/channel exports
- preserves the same message, reply, and attachment block semantics
- can be checked structurally with `python scripts/validate_export_docx.py --input-docx ... --json`
- the validator now checks:
  - required OOXML parts
  - XML parseability for XML and relationship parts
  - content-type overrides that point to real package parts
  - internal relationship targets that resolve to real package parts
  - exported style, hyperlink, reply-badge, and attachment-note signals
- canonical review artifacts can be regenerated in one command rather than through ad hoc manual sample rendering

## 6) One-shot semantic search -> full-day exports -> combined PDF/DOCX

```bash
python scripts/export_semantic_daypack.py \
  --workspace soylei \
  --terms "asphalt emulsions" "pure asphalt" "hawkseale" \
  --output-pdf exports/soylei-semantic-hits-daypack-auto.pdf \
  --output-docx exports/soylei-semantic-hits-daypack-auto.docx \
  --embed-attachments \
  --attach-files
```

Pipeline:
1. semantic/hybrid searches per term
2. collect channel/day bundles from hits
3. export each bundle via `export_channel_day.py`
4. render downstream formats from the same JSON bundle
5. combine via `export_multi_day_pdf.py`
