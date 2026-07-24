FROM python:3.13.14-slim-bookworm

ARG TERRAFORM_VERSION=1.15.8

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOME=/opt/fed-sysml \
    PIPELINE_INPUT_DIR=/pipeline/input \
    PIPELINE_OUTPUT_DIR=/pipeline/output \
    PYTHONPATH=/opt/fed-sysml/src

WORKDIR ${APP_HOME}

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        unzip \
    && terraform_arch="$(dpkg --print-architecture)" \
    && case "${terraform_arch}" in amd64|arm64) ;; *) echo "Unsupported Terraform architecture: ${terraform_arch}" >&2; exit 1 ;; esac \
    && terraform_zip="terraform_${TERRAFORM_VERSION}_linux_${terraform_arch}.zip" \
    && curl -fsSLo "/tmp/${terraform_zip}" "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/${terraform_zip}" \
    && curl -fsSLo /tmp/terraform_SHA256SUMS "https://releases.hashicorp.com/terraform/${TERRAFORM_VERSION}/terraform_${TERRAFORM_VERSION}_SHA256SUMS" \
    && cd /tmp \
    && grep " ${terraform_zip}$" terraform_SHA256SUMS | sha256sum -c - \
    && unzip "/tmp/${terraform_zip}" -d /usr/local/bin \
    && chmod +x /usr/local/bin/terraform \
    && terraform version \
    && rm -f "/tmp/${terraform_zip}" /tmp/terraform_SHA256SUMS \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY src ./src
COPY docker/entrypoint.sh /usr/local/bin/fed-sysml-entrypoint

RUN mkdir -p "${PIPELINE_INPUT_DIR}" "${PIPELINE_OUTPUT_DIR}" \
    && ln -sfn "${PIPELINE_INPUT_DIR}" "${APP_HOME}/input" \
    && ln -sfn "${PIPELINE_OUTPUT_DIR}" "${APP_HOME}/output" \
    && chmod +x /usr/local/bin/fed-sysml-entrypoint

WORKDIR ${APP_HOME}/src

VOLUME ["/pipeline/input", "/pipeline/output"]

ENTRYPOINT ["/usr/local/bin/fed-sysml-entrypoint"]
CMD ["generate"]

