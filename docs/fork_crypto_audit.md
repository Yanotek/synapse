# Cryptography Audit: Yanotek/synapse Fork vs Upstream

This document provides a comprehensive audit of cryptography-related differences between
this fork and upstream `element-hq/synapse` v1.114.0.

| | |
|---|---|
| **Fork** | `https://github.com/Yanotek/synapse.git` |
| **Upstream base** | Synapse v1.114.0 (squash commit `520dcf9e7`) |
| **Audit scope** | All branches, all custom commits, all files |
| **Conclusion** | **No crypto strengthening found. One change weakens encryption enforcement.** |

---

## Findings

### 1. Encryption Power Level Bypass (WEAKENING)

**File:** `synapse/event_auth.py` (line 807)
**Function:** `_can_send_event()`
**Status:** Present on `develop` branch

```python
# Upstream (strict):
if user_level < send_level:
    raise UnstableSpecAuthError(403, ...)

# This fork (bypass for encryption events):
if user_level < send_level and event.type != 'm.room.encryption' and event.type != 'm.room.request_calls_access':
    raise UnstableSpecAuthError(403, ...)
```

**Effect:** `m.room.encryption` state events are exempted from the generic power level
send check. Any user can attempt to send an encryption event regardless of the room's
`events` power level setting.

The room-specific encryption power level (`EventTypes.RoomEncryption: 100`) is still
enforced in a separate check, so this is a partial bypass of one of two auth layers.

**History:** Commits `6425c29f28` and `55d6ea0774` originally lowered the encryption
power level from 100 to 0 in `synapse/handlers/room.py`. Commit `51251122b5` reverted
the room handler change but left this auth bypass in `event_auth.py`.

**Assessment:** This is a **spec deviation that weakens** encryption authorization, not
strengthens it.

---

### 2. Custom Event Type Bypass

**File:** `synapse/event_auth.py` (line 807, same change as above)

`m.room.request_calls_access` — a non-standard event type (Yanotek-specific calling
feature) — also bypasses the generic power level check. This is not a standard Matrix
event type and has no cryptographic function.

---

## Areas Verified — No Changes Found

The following areas were exhaustively checked across **all branches** (`develop`,
`synapse-1.114.0`, `synapse-1.128.0`, `feature/allow-kick-same-power-level`,
`feature/sync-fork`, `feature/develop-backup-05-01-25`). No modifications were found.

### End-to-End Encryption

| Component | Files | Modified? |
|-----------|-------|-----------|
| E2E key management | `synapse/handlers/e2e_keys.py` | No |
| E2E room keys | `synapse/handlers/e2e_room_keys.py` | No |
| Olm/Megolm sessions | All related handlers | No |
| Device verification | All related handlers | No |
| Cross-signing | All related handlers | No |
| Key backup / secret storage | All related handlers | No |

### Cryptographic Primitives

| Component | Files | Modified? |
|-----------|-------|-----------|
| Event signing | `synapse/crypto/event_signing.py` | No |
| Key verification | `synapse/crypto/keyring.py` | No |
| TLS context | `synapse/crypto/context_factory.py` | No |
| Entire `synapse/crypto/` directory | All files | No |

### Federation Security

| Component | Files | Modified? |
|-----------|-------|-----------|
| Federation transport | `synapse/federation/transport/` | No |
| Federation HTTP client | `synapse/federation/` | No |
| Server ACL checking | `rust/src/acl/` | No |
| Request signing | All related files | No |

### Rust Crypto Code

| Component | Files | Modified? |
|-----------|-------|-----------|
| Push rules | `rust/src/push/` | No |
| ACL | `rust/src/acl/` | No |
| Events | `rust/src/events/` | No |
| HTTP signing | `rust/src/http.rs` | No |

### Configuration

| Component | Files | Modified? |
|-----------|-------|-----------|
| TLS config | `synapse/config/tls.py` | No |
| Key config | `synapse/config/key.py` | No |
| All config modules | `synapse/config/` (48 files) | No |
| Room encryption default power level | `synapse/handlers/room.py` (line ~1204) | No (still 100) |

### Dependencies

| Package | Modified? |
|---------|-----------|
| `cryptography` | No |
| `signedjson` | No |
| `unpaddedbase64` | No |
| `bcrypt` | No |
| `PyNaCl` | No |
| `pyproject.toml` | No |
| `poetry.lock` | No |

### Authentication

| Component | Files | Modified? |
|-----------|-------|-----------|
| Password hashing | All related files | No |
| Token management | All related files | No |
| SSO/OIDC/SAML | All related files | No |

---

## Summary

| Finding | Direction | Severity |
|---------|-----------|----------|
| `m.room.encryption` bypasses generic send-level check | **Weakens** | Medium |
| `m.room.request_calls_access` bypasses send-level check | Neutral (custom type) | Low |
| All other crypto: E2E, signing, TLS, keys, Rust code | **Unchanged** | — |

**This fork is cryptographically identical to upstream Synapse v1.114.0**, except for
one change in `event_auth.py` that partially weakens the power level gate on encryption
state events. No additional cryptographic protections, hardening, or features were added
in any branch.
