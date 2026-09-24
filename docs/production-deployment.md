# Production deployment — corpvitagroup.ru

This document describes the intended first production deployment after REG.RU account/domain verification is complete.

## Target server

Recommended starting VPS:

- Ubuntu 24.04 LTS;
- 4 vCPU;
- 8 GB RAM;
- 80–100 GB NVMe;
- public IPv4;
- provider snapshots/backups enabled.

PostgreSQL is not exposed to the public internet. Only ports 22, 80 and 443 are needed from outside.

## DNS

Create an A record:

`corpvitagroup.ru -> <SERVER_PUBLIC_IP>`

Wait until the DNS record resolves to the VPS before starting Caddy. Caddy obtains and renews TLS certificates automatically.

## Server preparation

Install Docker Engine and Docker Compose plugin from the official Docker repository. Configure SSH key access and disable password-based SSH after confirming key login.

Clone the repository into a dedicated directory, for example:

`/opt/vitagroup`

Create the real `.env` from `.env.example`. Never commit the real file.

Generate production secrets directly on the server. For example:

`openssl rand -hex 64`

Use the generated value for `AUTH_JWT_SECRET`. Generate a separate strong PostgreSQL password.

Real values that must exist only on the server include:

- POSTGRES_PASSWORD;
- AUTH_JWT_SECRET;
- COVERSE_API_TOKEN;
- YANDEX_PLAN_PUBLIC_URL;
- any future third-party API credentials.

## First start

From the repository root:

`docker compose build`

`docker compose up -d db migrate`

Check migration completion:

`docker compose ps`

`docker compose logs migrate`

The migrate container must exit successfully. Then start the remaining services:

`docker compose up -d`

Check:

`docker compose ps`

`docker compose logs --tail=100 backend caddy`

Open:

`https://corpvitagroup.ru/health`

Expected status: `ok`, database `ok`, and schema version `012_reconciliation_cases.sql` or a later migration.

## First administrator

Create the first administrator only on the server:

`docker compose exec backend python -m app.create_admin --email <ADMIN_EMAIL>`

Enter the temporary password interactively. The account requires a password change at first login.

Do not place the administrator password in shell history, GitHub, documentation, screenshots, or chat messages.

## Updates

Before an application update, ensure that a recent database backup exists.

Then:

`git pull --ff-only`

`docker compose build`

`docker compose up -d db migrate`

Verify that migration completed successfully.

Then:

`docker compose up -d`

Check `/health` and the application login.

The migration runner stores applied SQL files in `schema_migrations`, verifies their SHA-256 checksums and refuses to silently re-run a changed historical migration.

## Backups

The `backup` service creates a PostgreSQL custom-format dump immediately after startup and then every 24 hours.

Retention is controlled by:

`BACKUP_RETENTION_DAYS=14`

Backups are stored in the Docker volume `postgres_backups`.

Provider-level VPS snapshots should also be enabled. Database dumps and provider snapshots protect against different failure scenarios and should both be used.

To list backup files:

`docker compose exec backup ls -lh /backups`

A backup should periodically be copied to storage outside the VPS.

## Restore

Restoring replaces the current database and must be performed during maintenance.

Stop application writes first:

`docker compose stop backend`

Open a shell in a PostgreSQL client container with the backup volume mounted, then use `infra/restore-postgres.sh` with the chosen dump file.

After restore, run migrations and restart the application:

`docker compose up -d migrate`

`docker compose up -d backend frontend caddy`

Verify `/health` and perform a login/read-only smoke test before returning the system to users.

## Firewall

Allow:

- SSH only from trusted administrator networks where practical;
- TCP 80;
- TCP 443.

Do not expose PostgreSQL port 5432 publicly.

## Production checks

Before enabling users:

- DNS points to the VPS;
- HTTPS certificate is valid;
- `/health` returns database `ok`;
- migration container completed successfully;
- real production JWT secret is configured;
- PostgreSQL password is not the example value;
- demo mode is false;
- first administrator can sign in and is forced to change the temporary password;
- operator/QC/warehouse/accountant roles see only their own workspaces;
- a test DAY and NIGHT shift can be opened and read correctly;
- backup file is created and can be listed;
- Coverse and Yandex source credentials are configured only after the core site is healthy.

## Rollback principle

Application rollback and database rollback are separate operations.

For a frontend/backend regression, roll the application code back to the previous known-good commit only if the current database schema remains compatible.

For a destructive data/schema incident, stop writes and restore the latest verified database dump or provider snapshot. Do not edit already-applied numbered migration files on a production system.
