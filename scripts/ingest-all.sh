#!/usr/bin/env bash
# FinAgent — run both ingestion pipelines in sequence
# Sanctions graph first (FalkorDB), then document corpus (OpenSearch).
# The doc ingestor uses entity data from the graph for enrichment, so
# order matters — always run sanctions before docs.
#
# Usage:
#   bash scripts/ingest-all.sh               # sanctions + docs
#   bash scripts/ingest-all.sh --docs-only   # skip sanctions, docs only
#   bash scripts/ingest-all.sh --sanctions-only
set -euo pipefail
source "$(dirname "$0")/common.sh"

RUN_SANCTIONS=true
RUN_DOCS=true

for arg in "$@"; do
    case "$arg" in
        --docs-only)       RUN_SANCTIONS=false ;;
        --sanctions-only)  RUN_DOCS=false ;;
    esac
done

START=$(date +%s)

if [ "$RUN_SANCTIONS" = true ]; then
    bash "$(dirname "$0")/ingest-sanctions.sh"
fi

if [ "$RUN_DOCS" = true ]; then
    bash "$(dirname "$0")/ingest-docs.sh"
fi

END=$(date +%s)
ELAPSED=$(( (END - START) / 60 ))
info "All ingestion complete in ~${ELAPSED} minutes."
