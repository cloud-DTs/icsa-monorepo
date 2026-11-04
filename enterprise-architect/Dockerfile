FROM ubuntu:26.04

ENV DEBIAN_FRONTEND=noninteractive \
    HOME=/home/ea \
    WINEPREFIX=/home/ea/.wine \
    WINEDEBUG=-all \
    DISPLAY=:1

RUN dpkg --add-architecture i386 && \
    apt-get update && \
    apt-get install -y --no-install-recommends \
      ca-certificates \
      wget \
      gnupg2 \
      xvfb \
      x11vnc \
      fluxbox \
      novnc \
      websockify \
      wine \
      wine32 \
      wine64 \
      winbind \
      cabextract \
      unzip \
      p7zip-full \
      fonts-liberation \
      fonts-dejavu-core \
      xterm \
      && rm -rf /var/lib/apt/lists/*

RUN useradd -m -s /bin/bash ea && \
    mkdir -p /models && \
    chown -R ea:ea /models

USER ea

WORKDIR /home/ea

COPY --chown=ea:ea installer/ /tmp/installer/

RUN test -f /tmp/installer/EnterpriseArchitect.msi || \
      (echo "Put EnterpriseArchitect.msi into installer/ before building." && exit 1) && \
    xvfb-run -a sh -c 'wineboot --init && wine msiexec /i /tmp/installer/EnterpriseArchitect.msi /qn /norestart && wineboot --shutdown' && \
    rm -rf /tmp/installer

USER root

COPY entrypoint.sh /usr/local/bin/entrypoint.sh

RUN chmod +x /usr/local/bin/entrypoint.sh

USER ea

EXPOSE 5900 6080

ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
