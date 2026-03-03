# Rebase Plan: Fork Changes onto Upstream Synapse v1.148.0

This document describes the plan for rebasing the Yanotek fork's custom modifications
onto the latest upstream release of `element-hq/synapse`.

| | |
|---|---|
| **Current base** | Synapse v1.114.0 (squash commit `520dcf9e7`) |
| **Target base** | Synapse **v1.148.0** (latest stable release) |
| **Version gap** | 34 minor versions behind |
| **Files to port** | 9 files (8 modified + 1 new) |
| **Modifications** | 7 distinct changes |

---

## Why Not `git rebase`

A standard `git rebase` won't work here because:
- The "merge" commit `520dcf9e7` is a single-parent squash (not a real merge), so git
  can't cleanly identify which commits are "ours" vs upstream
- Some fork changes are baked into the squash commit tree, not in separate commits
- Changes span two branches (`develop` + `synapse-1.114.0`)

---

## Strategy: Manual Re-application on Clean v1.148.0 Base

Create a fresh branch from the `v1.148.0` tag and manually re-apply each of the 7
documented modifications. The changes are well-documented in `docs/fork_differences.md`
and most are small (1-20 lines). This avoids fighting with squash-commit history.

---

## Steps

### Step 1: Add upstream remote and fetch

```bash
git remote add upstream https://github.com/element-hq/synapse.git
git fetch upstream --tags
```

### Step 2: Create new branch from v1.148.0

```bash
git checkout -b develop-v1.148.0 v1.148.0
```

### Step 3: Apply each modification (7 changes, 9 files)

For each modification, read the v1.148.0 version of the file, locate the equivalent
code section, and apply the same semantic change. Ordered from simplest to most complex.

#### 3a. Public Room List Limit (1 line)
- **File:** `synapse/handlers/room_list.py`
- **Change:** `MAX_PUBLIC_ROOMS_IN_RESPONSE = 100` -> `100000`
- **Risk:** Trivial — just a constant

#### 3b. Profile Propagation Disabled (~6 lines)
- **File:** `synapse/handlers/profile.py`
- **Change:** Set `propagate: bool = False` (default) in `set_displayname()` and
  `set_avatar_url()`, comment out `_update_join_states()` calls
- **Risk:** Low — need to find the two methods, check if signature changed

#### 3c. Encryption & Custom Event Auth Bypass (~3 lines)
- **File:** `synapse/event_auth.py`
- **Change:** In `_can_send_event()`, add exceptions for `m.room.encryption` and
  `m.room.request_calls_access` event types to the power level check
- **Risk:** Medium — `event_auth.py` is heavily modified between versions. Need to find
  the equivalent `user_level < send_level` check in v1.148.0

#### 3d. One-on-One Room Kick Bypass (~50 lines)
- **File:** `synapse/event_auth.py`
- **Change:** Add `_is_one_on_one_room()` function and modify kick logic in
  `_is_membership_change_allowed()` to bypass kick restrictions in 2-member rooms
- **Risk:** Medium-High — same file as 3c, and upstream has changed auth rules for newer
  room versions. Need to find the right location in v1.148.0's auth flow

#### 3e. Push Notification Room Alias (~30 lines across 3 files)
- **File:** `synapse/push/presentable_names.py` — add `calculate_room_alias()` function
- **File:** `synapse/push/push_tools.py` — import and call `calculate_room_alias()`
- **File:** `synapse/push/httppusher.py` — add `room_alias` to push payload
- **Risk:** Medium — push system has been refactored in newer versions. Need to find
  equivalent payload construction point

#### 3f. Debug Endpoint (~71 lines, new file + registration)
- **File:** `synapse/rest/client/debug.py` — create new file (copy from fork)
- **File:** `synapse/rest/__init__.py` — add import and registration line
- **Risk:** Low — new file won't conflict. Registration line may need adjustment if
  `__init__.py` structure changed

#### 3g. Notifier Memory Leak Fix (~282 lines)
- **File:** `synapse/notifier.py`
- **Risk:** **HIGH** — this is the most complex change. However, it's possible that
  upstream v1.148.0 has already fixed this memory leak (34 versions later).
- **Action:** Compare the v1.148.0 `notifier.py` with the fork's patched version. If
  upstream already uses a different listener pattern or has fixed the empty-room cleanup,
  **skip this change entirely**.

### Step 4: Verify

```bash
# Linting
poetry run ./scripts-dev/lint.sh -d

# Type checking
poetry run mypy

# Run relevant tests
poetry run trial tests.rest.admin tests.handlers.test_profile tests.push

# Verify debug endpoint compiles
python -c "import synapse.rest.client.debug"
```

### Step 5: Commit

Create clean commits — one per logical modification for traceable history:

1. `feat: allow kick in 1:1 rooms (fork customization)`
2. `feat: bypass encryption/calls power level check (fork customization)`
3. `config: increase public rooms response limit to 100k`
4. `feat: disable profile propagation to rooms`
5. `feat: add room_alias to push notification payload`
6. `fix: notifier memory leak cleanup` (if still needed)
7. `feat: add debug endpoint for memory diagnostics`

---

## Files to Read Before Modifying

Before editing each file in v1.148.0, read it to understand what changed upstream:

| File | What to look for |
|------|-----------------|
| `synapse/event_auth.py` | `_can_send_event()` and `_is_membership_change_allowed()` |
| `synapse/handlers/room_list.py` | `MAX_PUBLIC_ROOMS_IN_RESPONSE` constant |
| `synapse/handlers/profile.py` | `set_displayname()` and `set_avatar_url()` signatures |
| `synapse/push/httppusher.py` | Push payload construction (`content[...]` assignments) |
| `synapse/push/presentable_names.py` | Existing function patterns for adding new one |
| `synapse/push/push_tools.py` | Notification context building (`ctx[...]` assignments) |
| `synapse/notifier.py` | Whether memory leak fix is still relevant in v1.148.0 |
| `synapse/rest/__init__.py` | Servlet registration pattern |

---

## Estimated Conflict Risk

| Modification | Lines | Risk | Notes |
|---|---|---|---|
| Room list limit | 1 | Trivial | Constant rename unlikely |
| Profile propagation | 6 | Low | Method signatures may have changed |
| Encryption bypass | 3 | Medium | `event_auth.py` heavily modified upstream |
| 1:1 kick bypass | 50 | Medium-High | Auth rules changed for new room versions |
| Push room alias | 30 | Medium | Push system refactored in newer versions |
| Debug endpoint | 73 | Low | New file, minimal registration wiring |
| Notifier fix | 282 | High | May already be fixed upstream — check first |

---

## Reference Documents

- `docs/fork_differences.md` — detailed description of each modification with code samples
- `docs/fork_crypto_audit.md` — cryptography audit (encryption bypass analysis)
- `docs/fork_migration_feasibility.md` — why module wrapper approach won't work
