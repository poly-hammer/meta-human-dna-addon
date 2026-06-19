# Installing Docker for the NLS Worker

The Raw Control Editor's **Match Joints to Mesh (ML)** operator runs Epic's
`nlstools` ML matcher in an isolated Python 3.11 process. The addon ships two
transports for that process, selectable in **Edit ▸ Preferences ▸ Add-ons ▸
Character DNA ▸ NLS Worker Transport**:

| Transport         | Platforms             | When to use                                                                                                   |
| ----------------- | --------------------- | ------------------------------------------------------------------------------------------------------------- |
| **System Python** | Windows, Linux        | You already have (or are willing to install) a CPython 3.11 on your host. Fast, zero container overhead.      |
| **Docker**        | Windows, Linux, macOS | You want a hands-off setup, can't install Python 3.11, or you're on macOS (which has no native NLS binaries). |

This page covers the Docker route.

## Prerequisites

* A 64-bit x86 host. (The worker image only ships for `linux/amd64`.)
* Free disk space for the worker image (~300 MB after build).
* On Windows: Docker Desktop 4.x or newer with the WSL 2 backend enabled.
* On macOS: Docker Desktop 4.x or newer.
* On Linux: Docker Engine 24+ (or Docker Desktop for Linux).

## Install

* **Windows / macOS:** download Docker Desktop from
  [docker.com/products/docker-desktop](https://www.docker.com/products/docker-desktop/)
  and run the installer. Launch Docker Desktop once and wait for the whale icon
  in the system tray to report *Docker Desktop is running*.
* **Linux:** follow the distro instructions at
  [docs.docker.com/engine/install](https://docs.docker.com/engine/install/).
  Make sure your user is in the `docker` group (`sudo usermod -aG docker $USER`,
  then log out + back in) so the addon can talk to the daemon without `sudo`.

## Verify

Open a terminal and run:

```sh
docker version
```

You should see both a Client and a Server section. If the Server section is
missing or reports an error, the daemon isn't running -- start Docker Desktop /
the `docker` service and try again.

## First Match Bones click

The first time you run **Match Joints to Mesh (ML)** with the Docker transport
selected, the addon will:

1. Probe the Docker daemon (cached for 30 s thereafter).
2. Build the worker image `character-dna-nls-worker:py311-v1` from the
   bundled `Dockerfile`. This downloads `python:3.11-slim` plus a handful of
   shared libraries and installs `numpy==1.26.4` -- typically 30 -- 60 s on a
   warm broadband connection.
3. Spawn the container, bind-mount the extracted Linux NLS package read-only
   at `/work/nls`, bind-mount your ML model directory read-only at
   `/work/models`, and start the worker on a free local port.

Subsequent Match Bones clicks skip steps (2) and re-use the cached container
for the rest of the Blender session. The container is labeled
`character_dna_worker=true` so a stale instance (e.g. after a Blender crash)
is automatically removed the next time you load the addon.

## Switching back to System Python

Open **Edit ▸ Preferences ▸ Add-ons ▸ Character DNA ▸ NLS Worker Transport**
and choose **System Python**. The dropdown is hidden on macOS because there
are no native NLS binaries for darwin.

## Troubleshooting

**`docker` CLI not found on PATH.** Install Docker Desktop / Engine and make
sure the installer added the CLI to your shell's `PATH`. On Linux this is
usually `/usr/bin/docker`.

**Docker is installed but the daemon is not reachable.** Start Docker Desktop
or run `sudo systemctl start docker`.

**Image build fails with a network error.** Docker pulled the base image
from Docker Hub; check your firewall / proxy settings. You can also pre-pull
the base image with `docker pull python:3.11-slim`.

**Linux NLS package missing.** Click **Extract Dependencies** in the addon
preferences. On Windows hosts extraction now lays down both the Windows and
Linux trees so you can switch between transports without re-extracting.
