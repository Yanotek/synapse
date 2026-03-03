# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Synapse is a Matrix homeserver implementation written in Python 3 with performance-critical components in Rust (via PyO3/Maturin). It uses Twisted for async I/O and the Trial test runner.

## Build & Development Commands

```bash
# Install dependencies (requires Python 3.8+, Rust toolchain, Poetry 1.3.2+)
poetry install --extras all

# Run the homeserver
poetry run python -m synapse.app.homeserver -c homeserver.yaml

# Rebuild Rust code after changes (faster than poetry install)
maturin develop

# Generate sample config
./scripts-dev/generate_sample_config.sh
```

## Testing

```bash
# Run all unit tests
poetry run trial tests

# Run tests in parallel (4 cores)
poetry run trial -j4 tests

# Run a specific test module
poetry run trial tests.rest.admin.test_room

# Run a specific test method
poetry run trial tests.handlers.test_admin.ExfiltrateData.test_invite

# Run tests against PostgreSQL (default is in-memory SQLite)
SYNAPSE_POSTGRES=1 SYNAPSE_POSTGRES_HOST=127.0.0.1 SYNAPSE_POSTGRES_USER=postgres SYNAPSE_POSTGRES_PASSWORD=secret poetry run trial tests

# Debug test output
SYNAPSE_TEST_LOG_LEVEL=DEBUG poetry run trial tests
less _trial_temp/test.log

# Persist SQLite DB for inspection after tests
SYNAPSE_TEST_PERSIST_SQLITE_DB=1 poetry run trial tests
sqlite3 _trial_temp/test.db
```

Test timeout is 20 seconds (set in `tests/__init__.py`).

## Linting & Type Checking

```bash
# Run all linters (modifies files in place): isort, black, ruff, clippy, rustfmt, mypy
poetry run ./scripts-dev/lint.sh

# Lint only files changed since last commit
poetry run ./scripts-dev/lint.sh -d

# Lint specific files
poetry run ./scripts-dev/lint.sh path/to/file.py

# Individual tools
poetry run isort synapse tests
poetry run black synapse tests
poetry run ruff check --fix synapse tests
poetry run mypy
```

## Code Style

- **Naming**: `CamelCase` for classes/types, `snake_case` for functions/variables
- **Docstrings**: Google style
- **Imports**: Import classes/functions directly (not modules). No wildcard or relative imports. isort sections: STDLIB, THIRDPARTY, TWISTED, FIRSTPARTY, TESTS
- **Line length**: 88 (enforced by black)
- **Type hints**: Required — mypy runs in strict mode (disallow_untyped_defs, strict_equality, etc.)
- **Config values**: Use `true`/`false` (not `True`/`False`) in YAML examples
- **Pydantic models**: Must use strict types (checked by `scripts-dev/check_pydantic_models.py`)

## Architecture

```
synapse/
├── app/              # Entry points: homeserver.py, generic_worker.py
├── handlers/         # Business logic (events, federation, presence, typing, rooms, etc.)
├── rest/             # HTTP/JSON API endpoints (client/, admin/, media/)
├── federation/       # Server-to-server communication (sending & receiving)
├── storage/          # Database layer
│   ├── databases/    #   main/ and state/ database definitions
│   ├── controllers/  #   High-level storage abstractions
│   ├── schema/       #   Database migrations (delta files)
│   └── engines/      #   PostgreSQL and SQLite backends
├── state/            # State resolution and conflict handling
├── events/           # Event types, validation, internal metadata
├── config/           # Configuration modules (one per feature area)
├── crypto/           # Event signing, TLS
├── replication/      # Multi-worker communication
├── push/             # Push notification logic
├── media/            # Media repository
├── module_api/       # Plugin/extension API for third-party modules
└── synapse_rust/     # Python stubs for Rust bindings (acl, push, events, http)

rust/src/             # Rust source: ACL checks, push rule evaluation, event parsing, HTTP signing
tests/                # Unit tests (Twisted Trial), mirrors synapse/ structure
```

**Key patterns:**
- Handlers contain business logic and are accessed via the homeserver object (`hs.get_*_handler()`)
- REST servlets map HTTP endpoints to handler calls
- Storage is split into a low-level database layer (`databases/`) and higher-level controllers (`controllers/`)
- Database migrations use numbered delta files in `storage/schema/`
- Workers can run as separate processes communicating via replication streams

## Changelog

All changes require a Towncrier changelog entry in `changelog.d/`. File format: `<PR_number>.<type>` where type is one of: `feature`, `bugfix`, `docker`, `doc`, `removal`, `misc`. Content should be a short description ending with `.` or `!`.

## Branch Policy

Base all changes on the `develop` branch. Do not rebase PRs — add new commits instead.
