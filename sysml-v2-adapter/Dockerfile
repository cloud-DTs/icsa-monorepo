FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY exporter/ .

RUN --mount=type=secret,id=gh_token \
    mkdir -p /root/.m2 \
    && printf '<settings><servers><server><id>cloud-dts</id><username>x</username><password>%s</password></server></servers></settings>' \
       "$(cat /run/secrets/gh_token)" > /root/.m2/settings.xml \
    && mvn -q -B package -DskipTests \
    && rm /root/.m2/settings.xml


FROM eclipse-temurin:21-jre
COPY --from=build /src/target/exporter-1.0-SNAPSHOT.jar /opt/exporter.jar

VOLUME ["/pipeline/input", "/pipeline/output", "/pipeline/code"]


ENTRYPOINT ["java", "-jar", "/opt/exporter.jar"]
CMD ["/pipeline/output", "/pipeline/input"]