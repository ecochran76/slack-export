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
- user avatar URLs when available, with initials fallback in the HTML report
- direct-message exports use participant-aware titles when both sides can be resolved
- human-readable timestamps
- HTML message bubbles with avatar rail and thread-reply styling
- consecutive messages from the same sender are visually grouped to reduce repeated avatar and metadata noise
- HTML header includes code-style tenant and channel identifiers, and replies render thread IDs as code-style metadata
- attachment rows keep the filename link but collapse long raw URLs into compact code-style file metadata plus a small preview link
- image attachments render inline at a bounded size and open in an in-page lightbox instead of navigating away
- Slack-native `email` attachments with embedded HTML previews are materialized into managed export bundles even when no binary file was downloaded locally
- hosted Slack attachments with `url_private_download` are opportunistically downloaded into the managed bundle when the file row exists but the mirror has not yet persisted a `local_path`
- if that direct download resolves to a Slack HTML/login interstitial instead of binary content, the exporter now rejects it and falls back to the original permalink rather than publishing a broken fake local asset
- HTML attachment hyperlinks + image thumbnails (3.5in wide)

Managed bundle mode:

```bash
PYTHONPATH=. ./.venv/bin/python scripts/export_channel_day.py \
  --config ~/.config/slack-mirror/config.yaml \
  --db ~/.local/state/slack-mirror/slack_mirror.db \
  --workspace default \
  --channel general \
  --day 2026-04-12 \
  --managed-export \
  --link-audience local
```

Managed bundle behavior:
- writes into `exports.root_dir/<export-id>/`
- uses deterministic export IDs such as `channel-day-default-general-2026-04-12-a1b2c3d4e5`
- copies local attachment files into the bundle under `attachments/...`
- if a hosted Slack attachment has no mirrored `local_path` yet, the exporter will use the configured workspace token and `url_private_download` to localize it into the bundle on demand
- that localization only succeeds when the configured token can actually download the file; missing `files:read` or inaccessible private files now degrade honestly instead of staging HTML as a bogus binary
- emits stable `download_url` / `public_url` plus audience-keyed `download_urls` and `preview_urls`
- uses `exports.local_base_url` and `exports.external_base_url` when configured, so one export bundle can serve both local and external consumers

Repair command for older mirrored files:

```bash
slack-mirror mirror reconcile-files --workspace default --auth-mode user --limit 100
slack-mirror mirror reconcile-files --workspace default --auth-mode user --limit 100 --json
```

- scans mirrored `files` rows with `url_private_download`
- skips rows that already have a real on-disk `local_path`
- attempts bounded repair downloads into the normal cache layout
- for Slack-for-Gmail `mode=email` containers, materializes the email body as local HTML and rewrites inline `files-email-priv` assets into a sibling local asset directory when those assets are token-downloadable
- updates `files.local_path` / `checksum` only on real binary success
- reports classified failure reasons such as `email_container`, `email_container_with_attachments`, `html_interstitial`, `not_found`, `forbidden`, and `timeout`

Download path contract:
- bundle HTML report: `/exports/<export-id>` or `/exports/<export-id>/`
- `/exports/<export-id>/<filepath>`
- preview path: `/exports/<export-id>/<filepath>/preview`
- API manifest paths:
  - `/v1/exports`
  - `/v1/exports/<export-id>`

Current preview support:
- images: inline browser preview
- PDFs: iframe browser preview
- `.docx`: HTML preview through `mammoth`
- `.pptx`: slide-by-slide HTML summary through the existing OOXML extraction layer
- `.xlsx`: sheet-table HTML summary through the existing OOXML extraction layer
- `.odt`: HTML text summary through the existing OpenDocument extraction layer
- `.odp`: slide-by-slide HTML summary through the existing OpenDocument extraction layer
- `.ods`: sheet-table HTML summary through the existing OpenDocument extraction layer
- text-like files (`text/*`, JSON, XML): escaped text preview
- other content types: explicit `PREVIEW_UNSUPPORTED`

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
- subtle paragraph shading on message and reply blocks to improve scanability without turning the export into a card-heavy layout
- thread-reply labeling and indentation
- tighter speaker/timestamp metadata alignment
- clickable attachment links now prefer explicit public/download URLs or Slack permalinks; local-only mirror files are rendered as labeled references instead of brittle `file://` links
- explicit paragraph styles for metadata, message body, reply body, and attachment blocks
- compact attachment-type badges plus human-readable metadata like `PDF document` or `Word document` instead of raw MIME strings
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

Attachment URL contract:
- the DOCX and PDF renderers now understand `public_url` and `download_url` attachment fields and prefer them over local mirror paths
- managed exports now emit `download_url` fields from config-backed base URLs when bundle mode is used
- managed exports now emit the same stable URL under `public_url` as the portable attachment-link field for downstream renderers
- managed exports now emit audience-keyed `download_urls` and `preview_urls` maps, with `download_url` / `preview_url` selected from the requested default audience
- the local API now serves bundle files under `/exports/<export-id>/<filepath>`
- the local API now exposes bundle manifests under `/v1/exports` and `/v1/exports/<export-id>` so the service owns the current configured URL contract
- preview URLs are now implemented in a bounded way for images, PDFs, and text-like files
- preview URLs now cover `.docx`, `.pptx`, `.xlsx`, `.odt`, `.odp`, and `.ods` without introducing a heavyweight office server dependency
- unsupported binary formats return `PREVIEW_UNSUPPORTED` instead of a broken browser experience
- the intended long-term direction is service-configured HTTP/HTTPS download URLs behind the live mirror deployment, so rendered exports can link to stable reverse-proxied attachment endpoints instead of filesystem paths

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
