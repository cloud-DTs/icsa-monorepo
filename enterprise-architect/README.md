# Enterprise Architect in Docker

This repository runs Sparx Systems Enterprise Architect in Wine inside a Linux
container. The desktop is exposed through noVNC at
<http://127.0.0.1:6080>.

## Requirements

- Docker Engine or Docker Desktop with Docker Compose
- An authorized Enterprise Architect MSI installer
- A valid Enterprise Architect license for each user

The Enterprise Architect application and installer are proprietary Sparx
Systems software and are not distributed by this repository.

## Prepare the installer

Download the installer through an authorized Sparx Systems channel and save it
as:

```text
installer/EnterpriseArchitect.msi
```

The MSI is ignored by Git but remains part of the local Docker build context.

## Build and run

Validate the Compose configuration:

```shell
docker compose config --quiet
```

Build the image and start Enterprise Architect:

```shell
docker compose up --build -d
```

Open <http://127.0.0.1:6080> in a browser.

Follow the container logs:

```shell
docker compose logs -f enterprise-architect
```

Stop the container without deleting the persistent Wine installation:

```shell
docker compose down
```

## Local directories

| Host directory | Directory visible in Enterprise Architect |
| --- | --- |
| `projects/` | `C:\users\ea\Documents\enterprise-architect\projects` |
| `input/` | `C:\users\ea\Documents\enterprise-architect\input` |
| `output/` | `C:\users\ea\Documents\enterprise-architect\output` |

Runtime files in `input/` and `output/` are intentionally ignored by Git.
Project databases in `projects/` are versioned.

## Reset the Wine installation

The installed application and Wine configuration are persisted in the
`enterprise-architect-wine` Docker volume. To remove that state and initialize
it again from a newly built image, run:

```shell
docker compose down -v
```

This permanently deletes the Wine volume and its local configuration.
