#!/bin/bash
# Run data retrieval, dataset generation, and reflection tasks.

set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

LOG_DIR="$SCRIPT_DIR/logs"
mkdir -p "$LOG_DIR"
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
LOG_FILE="$LOG_DIR/run_script_${TIMESTAMP}.log"
LOCK_FILE="$SCRIPT_DIR/.run_script.lock"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

acquire_lock() {
    if [ -f "$LOCK_FILE" ]; then
        log "ERROR: Lock file exists. Another instance may be running. Exiting."
        exit 1
    fi

    echo $$ > "$LOCK_FILE"
    log "Lock acquired (PID: $$)"
}

release_lock() {
    if [ ! -f "$LOCK_FILE" ]; then
        return
    fi

    LOCK_PID=$(cat "$LOCK_FILE" 2>/dev/null)
    if [ "$LOCK_PID" = "$$" ]; then
        rm -f "$LOCK_FILE"
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Lock released" >> "$LOG_FILE" 2>/dev/null || true
    else
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] Lock file belongs to PID: $LOCK_PID, not releasing" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

trap release_lock EXIT INT TERM
acquire_lock

log "Starting script execution"

if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
    PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
    log "Using venv Python at $PYTHON_BIN"
else
    PYTHON_BIN="$(command -v python3)"
    log "Using system Python at $PYTHON_BIN"
fi

export PYTHONPATH="$PROJECT_ROOT:$PYTHONPATH"

log "Running retrive_data.py..."
if "$PYTHON_BIN" "$SCRIPT_DIR/retrive_data.py" >> "$LOG_FILE" 2>&1; then
    log "retrive_data.py completed successfully"
else
    log "ERROR: retrive_data.py failed with exit code $?"
    exit 1
fi

log "Running generate_tabulated_data.py..."
if "$PYTHON_BIN" "$SCRIPT_DIR/generate_tabulated_data.py" --output "$PROJECT_ROOT/data/dataset.json" >> "$LOG_FILE" 2>&1; then
    log "generate_tabulated_data.py completed successfully"
else
    log "ERROR: generate_tabulated_data.py failed with exit code $?"
fi

log "Running reflection.py..."
if "$PYTHON_BIN" "$SCRIPT_DIR/reflection.py" >> "$LOG_FILE" 2>&1; then
    log "reflection.py completed successfully"
else
    log "ERROR: reflection.py failed with exit code $?"
fi

log "Script execution completed"

find "$LOG_DIR" -name "run_script_*.log" -type f | sort -r | tail -n +101 | xargs rm -f 2>/dev/null || true

release_lock
