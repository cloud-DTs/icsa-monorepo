# The SysML v2 kernel jar (0.55.0) is not on Maven Central. It is the file
# jupyter-sysml-kernel-0.55.0-all.jar of the public conda-forge package.
FROM alpine:3.20 AS kernel
RUN apk add --no-cache curl unzip zstd tar
RUN curl -fsSL -o /tmp/kernel.conda \
      https://conda.anaconda.org/conda-forge/noarch/jupyter-sysml-kernel-0.55.0-pyhd8ed1ab_0.conda \
    && echo "535a07e5768261cae5f09505acebae6663dfa883ff36539a9bde1bc8d514c1b2  /tmp/kernel.conda" | sha256sum -c - \
    && cd /tmp && unzip -q kernel.conda 'pkg-*.tar.zst' \
    && zstd -dc pkg-*.tar.zst | tar -x share/jupyter/kernels/sysml/jupyter-sysml-kernel-0.55.0-all.jar \
    && mv share/jupyter/kernels/sysml/jupyter-sysml-kernel-0.55.0-all.jar /jupyter-sysml-kernel.jar


FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
COPY --from=kernel /jupyter-sysml-kernel.jar /tmp/jupyter-sysml-kernel.jar
RUN mvn -q -B install:install-file -Dfile=/tmp/jupyter-sysml-kernel.jar \
      -DgroupId=org.omg.sysml -DartifactId=jupyter-sysml-kernel -Dversion=0.55.0 \
      -Dpackaging=jar -DgeneratePom=true
COPY exporter/ .

RUN mvn -q -B package -DskipTests


FROM eclipse-temurin:21-jre
COPY --from=build /src/target/exporter-1.0-SNAPSHOT.jar /opt/exporter.jar

VOLUME ["/pipeline/input", "/pipeline/output", "/pipeline/code"]


ENTRYPOINT ["java", "-jar", "/opt/exporter.jar"]
CMD ["/pipeline/output", "/pipeline/input"]