# syntax=docker/dockerfile:1

FROM maven:3.9-eclipse-temurin-25 AS build

WORKDIR /build

COPY pom.xml ./
RUN mvn -B -ntp dependency:go-offline

COPY src ./src
RUN mvn -B -ntp package dependency:copy-dependencies \
    -DincludeScope=runtime \
    -DoutputDirectory=target/dependency

FROM eclipse-temurin:25-jre

ARG APP_UID=10001
ARG APP_GID=10001

ENV APP_HOME=/opt/digital-twin-profile-sysml-v1 \
    PIPELINE_INPUT_DIR=/pipeline/input \
    PIPELINE_OUTPUT_DIR=/pipeline/output \
    PIPELINE_CODE_DIR=/pipeline/code \
    DTP_PATH_MAP=""

RUN mkdir -p "${APP_HOME}/classes" \
        "${APP_HOME}/lib" \
        "${PIPELINE_INPUT_DIR}" \
        "${PIPELINE_OUTPUT_DIR}" \
        "${PIPELINE_CODE_DIR}" \
    && chown -R "${APP_UID}:${APP_GID}" "${APP_HOME}" /pipeline

COPY --from=build --chown=${APP_UID}:${APP_GID} /build/target/classes/ /opt/digital-twin-profile-sysml-v1/classes/
COPY --from=build --chown=${APP_UID}:${APP_GID} /build/target/dependency/ /opt/digital-twin-profile-sysml-v1/lib/

USER ${APP_UID}:${APP_GID}
WORKDIR /pipeline/output

VOLUME ["/pipeline/input", "/pipeline/output", "/pipeline/code"]

ENTRYPOINT ["java", "-cp", "/opt/digital-twin-profile-sysml-v1/classes:/opt/digital-twin-profile-sysml-v1/lib/*", "Main"]
CMD ["/pipeline/input/model.xml", "dtwin"]
