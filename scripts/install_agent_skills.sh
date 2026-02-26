#!/usr/bin/env bash
set -euo pipefail

# Install repo-bundled Slack Mirror skills for multiple agent runtimes.
#
# Default targets (if present):
# - OpenClaw: ~/.openclaw/skills
# - Codex (conventional): ~/.codex/skills
# - Gemini CLI (conventional): ~/.gemini/skills
#
# Usage:
#   scripts/install_agent_skills.sh
#   scripts/install_agent_skills.sh --target ~/.openclaw/skills --target ~/.codex/skills
#   scripts/install_agent_skills.sh --dry-run

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC_DIR="${ROOT_DIR}/agent-skills"
DRY_RUN="false"
TARGETS=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGETS+=("$2")
      shift 2
      ;;
    --dry-run)
      DRY_RUN="true"
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "${SRC_DIR}" ]]; then
  echo "Missing source dir: ${SRC_DIR}" >&2
  exit 1
fi

if [[ ${#TARGETS[@]} -eq 0 ]]; then
  TARGETS=(
    "${HOME}/.openclaw/skills"
    "${HOME}/.codex/skills"
    "${HOME}/.gemini/skills"
  )
fi

echo "Source: ${SRC_DIR}"

for target in "${TARGETS[@]}"; do
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[dry-run] would install to: ${target}"
    continue
  fi

  mkdir -p "${target}"
  rsync -a --delete "${SRC_DIR}/" "${target}/"
  echo "Installed skills to: ${target}"

done

echo "Done."
