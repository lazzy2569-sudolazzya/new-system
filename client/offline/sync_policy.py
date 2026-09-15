"""Per-endpoint rule for how a stale cached read may be used while offline.

Gap in the original plan: it correctly bans queuing non-commutative writes
(invoice numbers must come from the server), but says nothing about a
stale *read* driving a write that becomes wrong once replayed -- e.g. a
storekeeper seeing a cached "50 units available" that another terminal has
since sold, and issuing stock against it before reconnecting.

Every screen that reads then writes must declare which bucket its read
falls into:

  STALE_OK        -- the write is purely additive/commutative, so acting on
                     a stale read is safe (e.g. recording a goods receipt).
  REQUIRES_FRESH   -- the write depends on the read being current, so the
                     action must be blocked until a live server read
                     succeeds (e.g. issuing stock against a low remaining
                     balance, or anything that can go negative if two
                     terminals act on the same stale number).

This module holds no business logic itself -- inventory/purchasing/sales
modules register their own endpoints' policy here as they're built in
later phases.
"""
from enum import Enum


class StalePolicy(Enum):
    STALE_OK = "stale_ok"
    REQUIRES_FRESH = "requires_fresh"


# Populated by each domain module as it lands (phase 2+). Empty for now --
# phase 1 has no business-data reads yet, only auth.
_ENDPOINT_STALE_POLICY: dict[str, StalePolicy] = {}


def register_policy(endpoint: str, policy: StalePolicy) -> None:
    _ENDPOINT_STALE_POLICY[endpoint] = policy


def policy_for(endpoint: str) -> StalePolicy:
    """Fail safe: an endpoint with no registered policy is REQUIRES_FRESH,
    not STALE_OK. An unrecognized read should never silently be trusted to
    drive a write.
    """
    return _ENDPOINT_STALE_POLICY.get(endpoint, StalePolicy.REQUIRES_FRESH)
