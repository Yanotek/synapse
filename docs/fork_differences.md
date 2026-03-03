# Fork Differences: Yanotek/synapse vs element-hq/synapse

This document describes the custom modifications in this fork compared to the upstream
[element-hq/synapse](https://github.com/element-hq/synapse) repository.

| | |
|---|---|
| **Fork origin** | `https://github.com/Yanotek/synapse.git` |
| **Upstream base** | Synapse **v1.148.0** (rebased from v1.114.0, March 2026) |
| **Contributors** | Joknek, daniil, skazancev |
| **Total custom commits** | ~15 (across all branches) |

---

## Table of Contents

1. [Branch Topology](#1-branch-topology)
2. [Custom Modifications on `develop`](#2-custom-modifications-on-develop)
   - [2.1 One-on-One Room Kick Permissions](#21-one-on-one-room-kick-permissions)
   - [2.2 Encryption and Custom Event Auth Bypass](#22-encryption-and-custom-event-auth-bypass)
   - [2.3 Public Room List Limit Increase](#23-public-room-list-limit-increase)
   - [2.4 Profile Propagation Disabled](#24-profile-propagation-disabled)
   - [2.5 Push Notification Room Alias](#25-push-notification-room-alias)
3. [Patches on `synapse-1.114.0` Branch](#3-patches-on-synapse-11140-branch)
   - [3.1 Notifier Memory Leak Fix](#31-notifier-memory-leak-fix)
   - [3.2 Debug Endpoint](#32-debug-endpoint)
4. [Summary Table](#4-summary-table)
5. [Upstream Sync Notes](#5-upstream-sync-notes)

---

## 1. Branch Topology

```
element-hq/synapse v1.114.0
  |
  +-- 520dcf9e7 "Merge Synapse 1.114.0" (Joknek) [see note below]
  |     |
  |     +-- develop  (current main branch)
  |     |     +-- a9312d088  feat: allow kick same power level
  |     |     +-- 4ab10412c  feat: power level < 100 restriction
  |     |     +-- 7f6c320a9  change kick rules
  |     |     +-- b78e8ba49  enable kicks in 1:1 rooms
  |     |     +-- (6 fix commits for 1:1 room detection)
  |     |     +-- 2fbe1d3af  restore previous changes (profile, room_list, push)
  |     |
  |     +-- synapse-1.114.0  (additional patches, not on develop)
  |           +-- add236e8f  add debug endpoint
  |           +-- 1df6a9936  fix notifier
  |           +-- c0b16da60  fix memory leak in notifier.py
  |
  +-- synapse-1.128.0  (tracks upstream v1.128.0, no custom patches ported yet)
```

**Important git history note:** Commit `520dcf9e7` ("Merge Synapse 1.114.0") is **not a real
git merge** — it is a single-parent squash commit. Its parent is `134611e3ef` (the last 1:1
kick fix commit). This means several fork modifications (`event_auth.py` auth bypass,
`push/presentable_names.py`, `push/push_tools.py`, `rest/__init__.py`) were baked into the
tree at or before this commit and are not visible in `git diff 520dcf9e7..HEAD`. The actual
fork divergence from upstream includes all changes listed in this document.

**No upstream remote is configured.** Only `origin` pointing to the Yanotek fork.

---

## 2. Custom Modifications on `develop`

These changes are live on the current working branch.

### 2.1 One-on-One Room Kick Permissions

**File:** `synapse/event_auth.py` (lines 695-742)

**What changed:** Two modifications to the membership change authorization logic in
`_is_membership_change_allowed()`:

1. **New function `_is_one_on_one_room()`** — counts joined members in auth events. If
   exactly 2 members are joined, kick restrictions are bypassed entirely:

```python
def _is_one_on_one_room(auth_events: StateMap["EventBase"]) -> bool:
    members = [
        state_key
        for (event_type, state_key), event in auth_events.items()
        if event_type == EventTypes.Member and event.membership == Membership.JOIN
    ]
    return len(members) == 2
```

2. **Modified power level logic for kicks** — the original upstream check
   `user_level < kick_level or user_level <= target_level` was replaced with:

```python
if not _is_one_on_one_room(auth_events):
    kick_level = get_named_level(auth_events, "kick", 50)
    if user_level < kick_level or (user_level < 100 and user_level <= target_level):
        raise AuthError(403, "You cannot kick user %s." % target_user_id)
```

This means:
- In **1:1 rooms** (exactly 2 joined members): kicks are always allowed, regardless of
  power levels.
- In **group rooms**: users with power level >= 100 can kick anyone at or below their level.
  Users with power level < 100 can only kick those with **strictly lower** power.

**Commits:** `a9312d088`, `4ab10412c`, `7f6c320a9`, `b78e8ba49`, + 6 fix commits by daniil

**Impact:** This is a **Matrix spec deviation**. Upstream Synapse enforces the standard
kick rules where `user_level >= kick_level AND user_level > target_level`. This change
affects event authorization, which means:
- Federated servers using standard rules may reject events that this fork considers valid.
- Events created under these custom rules may fail auth checks on other homeservers.

---

### 2.2 Encryption and Custom Event Auth Bypass

**File:** `synapse/event_auth.py` (line 807)

**What changed:** The `_can_send_event()` function was modified to exempt two event types
from the standard power level check:

```python
# Upstream:
if user_level < send_level:
    raise UnstableSpecAuthError(403, ...)

# This fork:
if user_level < send_level and event.type != 'm.room.encryption' and event.type != 'm.room.request_calls_access':
    raise UnstableSpecAuthError(403, ...)
```

This means:
- **`m.room.encryption`** events bypass the generic send-level power check. Any user can
  attempt to send an encryption state event regardless of the room's `events` power level
  setting. However, the specific power level for `EventTypes.RoomEncryption` (default 100)
  is still enforced separately in the power levels state event check.
- **`m.room.request_calls_access`** is a custom, non-standard Matrix event type (Yanotek-specific
  calling feature) that also bypasses power level checks.

**History:** This is a remnant of a reverted change. Commits `6425c29f28` and `55d6ea0774`
originally lowered the encryption power level from 100 to 0 in `synapse/handlers/room.py`.
Commit `51251122b5` reverted the room handler change but left this auth bypass in place.

**Impact:** This is a **Matrix spec deviation**. The bypass partially weakens the power level
gate on room encryption state events, though in practice the specific encryption power level
(100) still applies. The `m.room.request_calls_access` exception is for a non-standard
Yanotek feature.

---

### 2.3 Public Room List Limit Increase

**File:** `synapse/handlers/room_list.py` (line 59)

**What changed:**

```python
# Upstream:
MAX_PUBLIC_ROOMS_IN_RESPONSE = 100

# This fork:
MAX_PUBLIC_ROOMS_IN_RESPONSE = 100000
```

**Impact:** The `/publicRooms` API can now return up to 100,000 rooms in a single response
instead of the upstream limit of 100. This may cause performance issues with large room
directories due to increased memory usage and response serialization time. Consider using
pagination instead if the room count is high.

---

### 2.4 Profile Propagation Disabled

**File:** `synapse/handlers/profile.py` (lines 161, 222-223, 324-325)

**What changed:** Two modifications in the `ProfileHandler`:

1. **Default `propagate` parameter changed from `True` to `False`** in both
   `set_displayname()` and `set_avatar_url()`:

```python
# Upstream:
async def set_displayname(self, ..., propagate: bool = True) -> None:

# This fork:
async def set_displayname(self, ..., propagate: bool = False) -> None:
```

2. **Calls to `_update_join_states()` commented out** in both methods:

```python
# if propagate:
#     await self._update_join_states(requester, target_user)
```

**Impact:** When a user changes their display name or avatar, the change is saved to their
profile but is **no longer propagated** to their membership events in joined rooms. This means:
- Other users in rooms will see the **old** display name/avatar until the user sends a new event.
- Reduces federation traffic (no membership state updates on profile changes).
- The `_update_join_states` function still exists but is unreachable.

---

### 2.5 Push Notification Room Alias

**Files:**
- `synapse/push/presentable_names.py` (line 42+) — new function
- `synapse/push/push_tools.py` (lines 25, 107-111) — imports and usage
- `synapse/push/httppusher.py` (lines 499-500) — payload addition

**What changed:** Added a new function `calculate_room_alias()` in `presentable_names.py`
that extracts the canonical alias from room state. This is called in `push_tools.py` during
notification context building:

```python
room_alias = await calculate_room_alias(
    storage.main, room_state_ids, user_id, fallback_to_single_member=False
)
if room_alias:
    ctx["room_alias"] = room_alias
```

The alias is then included in the HTTP push notification payload in `httppusher.py`:

```python
if "room_alias" in ctx and len(ctx["room_alias"]) > 0:
    content["room_alias"] = ctx["room_alias"]
```

**Impact:** Push notifications now include a `room_alias` field (e.g., `#general:example.com`)
alongside `room_name` and `sender_display_name`. Mobile clients consuming the push gateway
payload can display the room alias. This is an additive change with no upstream compatibility
risk.

---

## 3. Patches on `synapse-1.114.0` Branch

These modifications exist on the `origin/synapse-1.114.0` branch but are **NOT currently
merged into `develop`**.

### 3.1 Notifier Memory Leak Fix

**File:** `synapse/notifier.py`

**What changed:** Refactored the `_NotifierUserStream` class to fix a memory leak in
long-running homeservers:

- Replaced `ObservableDeferred` wrapper with a direct `set` of `Deferred` objects for
  listener tracking.
- Added a `canceller` callback to properly clean up timed-out listeners.
- Added cleanup in `remove()` to pop empty room entries from `room_to_user_streams`,
  preventing unbounded growth of the room tracking dictionary.
- Renamed `notify()` to `update_and_fetch_deferreds()` for clarity.

**Commits:** `1df6a99362` (fix notifier), `c0b16da607` (fix memory leak)

**Impact:** Critical stability fix. Without this patch, `room_to_user_streams` accumulates
empty entries for rooms that no longer have active listeners, causing gradual memory growth
over days/weeks of uptime.

---

### 3.2 Debug Endpoint

**Files:**
- `synapse/rest/client/debug.py` (new file, 71 lines)
- `synapse/rest/__init__.py` (modified — added debug servlet registration)

**What changed:** Added a custom REST endpoint for runtime debugging:

```
GET /_matrix/client/v3/debug/Wf6dzZKXwL
```

The endpoint returns:
- **`top50`**: Top 50 memory allocations by line (via `tracemalloc`).
- **`stucked_deferreds`**: Count of Deferred objects that are called but have `None` result
  with `_suppressAlreadyCalled` set — indicates leaked/stuck async operations.
- **`empty_rooms`**: Count of empty entries in `notifier.room_to_user_streams`.
- **`all_rooms`**: Total rooms tracked by the notifier.

The endpoint uses a hardcoded random string (`Wf6dzZKXwL`) in the URL path as a basic
access control mechanism. Note: `tracemalloc.start()` is called when the servlet registers,
which adds ~10-30% memory overhead.

**Commit:** `add236e8f3`

**Impact:** Useful for diagnosing memory leaks and stuck async operations in production.
Should not be exposed publicly.

---

## 4. Summary Table

| # | Modification | File(s) | Branch | Category | Upstream Risk |
|---|---|---|---|---|---|
| 1 | 1:1 room kick bypass | `synapse/event_auth.py` | `develop` | Spec deviation | **High** — changes auth rules, affects federation |
| 2 | Encryption / custom event auth bypass | `synapse/event_auth.py` | `develop` | Spec deviation | **Medium** — weakens encryption power gate |
| 3 | Public rooms limit 100 -> 100k | `synapse/handlers/room_list.py` | `develop` | Config | **Low** — local behavior only |
| 4 | Disable profile propagation | `synapse/handlers/profile.py` | `develop` | Behavior change | **Medium** — stale profiles in rooms |
| 5 | Push notification room alias | `synapse/push/httppusher.py`, `presentable_names.py`, `push_tools.py` | `develop` | Enhancement | **Low** — additive payload field |
| 6 | Notifier memory leak fix | `synapse/notifier.py` | `synapse-1.114.0` | Bug fix | **None** — pure fix |
| 7 | Debug endpoint | `synapse/rest/client/debug.py` | `synapse-1.114.0` | Tooling | **None** — additive |
| — | Debug servlet registration | `synapse/rest/__init__.py` | `synapse-1.114.0` | Wiring | **None** — additive |

**Total files modified from upstream:** 8 modified + 1 new = **9 files**.

The full list of files that differ from upstream Synapse v1.114.0:
1. `synapse/event_auth.py` — kick bypass + encryption/event auth bypass
2. `synapse/handlers/room_list.py` — public rooms limit
3. `synapse/handlers/profile.py` — profile propagation disabled
4. `synapse/push/httppusher.py` — push room alias payload
5. `synapse/push/presentable_names.py` — `calculate_room_alias()` function
6. `synapse/push/push_tools.py` — room alias integration
7. `synapse/notifier.py` — memory leak fix
8. `synapse/rest/__init__.py` — debug servlet registration
9. `synapse/rest/client/debug.py` — new file (debug endpoint)

---

## 5. Upstream Sync Notes

### Current State

- The `develop` branch is based on upstream **v1.114.0** (released August 2024).
- A `synapse-1.128.0` branch tracks upstream v1.128.0 but custom patches have not been ported.
- The upstream is currently at **v1.128.0+** — this fork is approximately **14 minor versions behind**.

### Recommended Actions

1. **Add upstream remote:**
   ```bash
   git remote add upstream https://github.com/element-hq/synapse.git
   git fetch upstream
   ```

2. **Merge patches from `synapse-1.114.0` into `develop`:**
   The notifier memory leak fix (3.1) and debug endpoint (3.2) are on a separate branch
   and should be cherry-picked or merged into `develop` if they are intended for production.

3. **Expected merge conflicts when upgrading upstream:**
   - `synapse/event_auth.py` — heavily modified in upstream (auth rule changes, new room
     versions). The `_is_one_on_one_room` function and custom kick logic will need manual
     re-application.
   - `synapse/notifier.py` — has had significant refactoring upstream.
   - `synapse/handlers/profile.py` — minor upstream changes but the commented-out code
     will conflict.
   - `synapse/push/` — push system has been refactored in newer upstream versions.

4. **Consider upstreaming the memory leak fix** — if the issue exists in upstream Synapse,
   it could be contributed as a pull request to `element-hq/synapse`.
