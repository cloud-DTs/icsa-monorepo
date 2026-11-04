FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/opt/digital-twin-manager \
    DIGITAL_TWIN_MANAGER_CONFIG_DIR=/pipeline/input \
    DIGITAL_TWIN_MANAGER_STATE_DIR=/pipeline/output/.digital-twin-manager-state \
    PIPELINE_INPUT_DIR=/pipeline/input \
    PIPELINE_OUTPUT_DIR=/pipeline/output \
    PIPELINE_CODE_DIR=/pipeline/code \
    PYTHONPATH=/opt/digital-twin-manager/src

WORKDIR ${APP_HOME}

COPY --from=ghcr.io/astral-sh/uv:0.12.3 /uv /uvx /bin/

COPY pyproject.toml uv.lock ./

RUN uv sync --locked --no-dev --no-cache

COPY src ./src
COPY lambda_functions ./lambda_functions
COPY dependency/template.json ./dependency/

ENV PATH="/opt/digital-twin-manager/.venv/bin:${PATH}"

RUN mkdir -p \
    "${PIPELINE_INPUT_DIR}" \
    "${PIPELINE_OUTPUT_DIR}" \
    "${PIPELINE_CODE_DIR}" \
    "${DIGITAL_TWIN_MANAGER_STATE_DIR}"

WORKDIR ${PIPELINE_OUTPUT_DIR}

VOLUME ["/pipeline/input", "/pipeline/output", "/pipeline/code"]

ENTRYPOINT ["python", "/opt/digital-twin-manager/src/main.py"]
