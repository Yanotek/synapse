# Migration Feasibility: Replacing Fork with Upstream Synapse + Module Wrapper

This document evaluates whether the custom modifications in this fork could be
reimplemented as external Synapse modules, allowing the project to use upstream
`element-hq/synapse` as an unmodified dependency.

---

## Conclusion

**Migration is not feasible.** 5 of 7 fork modifications touch core internals that
the Synapse Module API cannot reach. Only the debug endpoint can be cleanly extracted
into a module.

---

## Per-Modification Assessment

### 1. One-on-One Room Kick Bypass — Impossible as Module

**Current:** Modifies `_is_membership_change_allowed()` in `synapse/event_auth.py`

**Why it fails:** The Module API's `check_event_allowed()` callback runs *after* core
authorization checks have already passed. The kick is rejected inside `event_auth.py`
before any module code ever executes. There is no pre-auth hook that could intercept
or override `_is_membership_change_allowed()`.

**Would require:** A new upstream Module API callback at the event authorization layer,
which upstream would likely reject since it would allow modules to break Matrix spec
compliance and federation consensus.

---

### 2. Encryption Event Auth Bypass — Impossible as Module

**Current:** Modifies `_can_send_event()` in `synapse/event_auth.py`

**Why it fails:** Same as above — `_can_send_event()` runs before any module callbacks.
The Module API has no hook to override power level enforcement for specific event types.

**Would require:** New pre-auth callback in upstream, unlikely to be accepted.

---

### 3. Public Room List Limit — Partial Workaround

**Current:** Changes `MAX_PUBLIC_ROOMS_IN_RESPONSE` from 100 to 100,000 in
`synapse/handlers/room_list.py`

**Module approach:** Could use `check_visibility_can_be_modified()` to control which
rooms are published, but cannot control the API response limit itself. The constant
is hardcoded with no config option.

**Verdict:** Cannot replicate the exact behavior. The upstream 100-room limit would
still apply per response; clients would need to paginate.

---

### 4. Profile Propagation Disabled — Impossible as Module

**Current:** Disables `_update_join_states()` in `synapse/handlers/profile.py`

**Why it fails:** The `on_profile_update()` module callback fires *after* propagation
has already happened. There is no callback to suppress or intercept the propagation
of profile changes to room membership events.

**Would require:** New upstream callback for federation propagation control.

---

### 5. Push Notification Room Alias — Impossible as Module

**Current:** Adds `room_alias` field to push payloads in `synapse/push/httppusher.py`,
`presentable_names.py`, and `push_tools.py`

**Why it fails:** The push notification system (`synapse/push/`) has **zero module
hooks**. There is no callback to intercept or modify push notification payloads before
they are sent. The Module API's `send_http_push_notification()` only allows sending
*additional* notifications, not modifying existing ones.

**Would require:** New upstream push payload customization callback.

---

### 6. Notifier Memory Leak Fix — Impossible as Module

**Current:** Refactors listener cleanup in `synapse/notifier.py`

**Why it fails:** This is a core bug fix to internal memory management. Modules cannot
patch or override the notifier's deferred tracking. This is not a feature — it's a fix.

**Correct approach:** Propose the fix upstream or cherry-pick on each upgrade.

---

### 7. Debug Endpoint — Easy as Module

**Current:** New file `synapse/rest/client/debug.py`

**Module approach:** Use `ModuleApi.register_web_resource()` to register a custom
Twisted `Resource` under `/_synapse/client/debug/`. The module would have full access
to the homeserver internals via the `ModuleApi` instance.

```python
class DebugModule:
    def __init__(self, config, api):
        api.register_web_resource(
            "/_synapse/client/debug",
            DebugResource(api)
        )
```

**Verdict:** Straightforward. This is the one modification that should be extracted
into a module regardless of migration decision.

---

## Summary Table

| # | Modification | As Module? | Difficulty |
|---|---|---|---|
| 1 | 1:1 room kick bypass | **Impossible** | No pre-auth hook exists |
| 2 | Encryption auth bypass | **Impossible** | No pre-auth hook exists |
| 3 | Public rooms limit 100k | **Partial** | Can't control response limit |
| 4 | Profile propagation off | **Impossible** | No propagation hook exists |
| 5 | Push room alias | **Impossible** | Zero hooks in push system |
| 6 | Notifier memory fix | **Impossible** | Core bug fix, not a feature |
| 7 | Debug endpoint | **Easy** | `register_web_resource()` |

---

## Alternative Approaches

### Option A: Keep the Fork (Recommended)

Continue maintaining the fork with periodic upstream merges.

- **Effort:** Low — only 9 files to rebase on upgrades
- **Risk:** Merge conflicts primarily in `event_auth.py` (heavily modified in upstream)
- **Benefit:** Full control, no API limitations

### Option B: Upstream + Monkeypatch at Runtime

Install upstream Synapse, then monkeypatch the 5 internal functions at startup via a
custom module that replaces function references.

- **Effort:** Medium initial, high ongoing maintenance
- **Risk:** Breaks silently on any upstream refactor of patched functions
- **Benefit:** Clean dependency management
- **Verdict:** Fragile, not recommended for production

### Option C: Propose Module API Extensions Upstream

Request new callbacks in the Synapse Module API for:
- Pre-authorization event validation (before power level checks)
- Push notification payload customization
- Profile federation propagation control

- **Effort:** Significant — requires upstream engagement and acceptance
- **Timeline:** Months to years
- **Risk:** The kick bypass specifically would likely be rejected as a spec violation
- **Verdict:** Worth proposing for push and profile hooks; unlikely for auth bypass

### Option D: Redesign at Application Layer

Drop the homeserver-level modifications and handle the behaviors differently:
- **Kicks in 1:1 rooms:** Handle "blocking" at the application/client layer instead of
  Matrix kicks. Use `m.room.ignore` or a custom application-level block list.
- **Profile propagation:** Accept the federation traffic or implement client-side caching.
- **Push room alias:** Fetch room alias in the mobile app separately from the push payload.
- **Room list limit:** Use client-side pagination.

- **Effort:** Significant product/client rework
- **Benefit:** No fork maintenance, always on latest upstream
- **Verdict:** Most sustainable long-term, but requires product changes

---

## Why This Fork Exists

The fork was created for one primary reason: **custom kick rules in 1:1 rooms** for a
consumer messaging product. Standard Matrix does not allow kicking a user from a direct
message when both users have equal power levels. This is a spec-level authorization rule
that upstream would not change, making a fork the only option.

The other modifications (profile propagation, push alias, room list limit) are secondary
operational customizations that accumulated alongside the core feature. None of them
individually would justify maintaining a fork.
