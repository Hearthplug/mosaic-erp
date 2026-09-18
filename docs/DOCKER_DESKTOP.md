# Run Mosaic with Docker Desktop

This path is for a business owner trying Mosaic on one computer. It does not require Kubernetes.

1. Install Docker Desktop from the official guide for [Windows](https://docs.docker.com/desktop/setup/install/windows-install/), [macOS](https://docs.docker.com/desktop/setup/install/mac-install/), or [Linux](https://docs.docker.com/desktop/setup/install/linux/).
2. Open Docker Desktop and wait until it says the engine is running.
3. Download this repository, open a terminal in its folder, and run `docker compose up --build`.
4. Open the address printed by Compose in your browser, create the owner account, and complete the guided setup.
5. Stop Mosaic with `docker compose down`. Your local data remains in the configured volume. Back it up before upgrades.

Docker's [run an application tutorial](https://docs.docker.com/get-started/tutorials/run-an-app/) explains images, containers, ports and stopping an app. This is a local evaluation path. A multi-user production deployment still needs PostgreSQL, HTTPS, backups, monitoring and tested recovery.
