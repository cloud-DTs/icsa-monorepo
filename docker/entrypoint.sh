#!/usr/bin/env bash
set -euo pipefail

if [[ -f "${APP_HOME}/src/paho_layer.zip" && ! -f "${PIPELINE_OUTPUT_DIR}/paho_layer.zip" ]]; then
    cp "${APP_HOME}/src/paho_layer.zip" "${PIPELINE_OUTPUT_DIR}/paho_layer.zip"
fi

case "${1:-generate}" in
    generate)
        if [[ $# -gt 0 ]]; then
            shift
        fi
        cd "${APP_HOME}/src"
        exec python main.py "$@"
        ;;
    terraform)
        shift
        cd "${PIPELINE_OUTPUT_DIR}"
        exec terraform "$@"
        ;;
    *)
        exec "$@"
        ;;
esac
