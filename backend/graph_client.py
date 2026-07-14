"""
Microsoft Graph API client for M365Mind.

Pulls governance policies from a Microsoft 365 tenant using a
delegated access token obtained via backend/auth.py.

Endpoints used
--------------
  GET /identity/conditionalAccess/policies
      Requires: Policy.Read.All
  GET /identity/conditionalAccess/namedLocations
      Requires: Policy.Read.All
  GET /security/informationProtection/sensitivityLabels
      Requires: InformationProtectionPolicy.Read.All

All endpoints are v1.0 (stable, not beta).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

_GRAPH_BASE = "https://graph.microsoft.com/v1.0"
_TIMEOUT    = 30.0


def _headers(access_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {access_token}",
        "Content-Type":  "application/json",
    }


def _get(url: str, access_token: str) -> list[dict]:
    """
    GET a Graph API endpoint, following @odata.nextLink for pagination.
    Returns the aggregated list of value items.
    """
    results: list[dict] = []
    next_url: str | None = url

    with httpx.Client(timeout=_TIMEOUT) as client:
        while next_url:
            resp = client.get(next_url, headers=_headers(access_token))
            resp.raise_for_status()
            data = resp.json()
            results.extend(data.get("value", []))
            next_url = data.get("@odata.nextLink")

    return results


# ── Public pull functions ─────────────────────────────────────────────────────

def get_conditional_access_policies(access_token: str) -> list[dict]:
    """
    Fetch all Conditional Access policies from the tenant.
    Returns raw Graph API objects.
    """
    url = f"{_GRAPH_BASE}/identity/conditionalAccess/policies"
    policies = _get(url, access_token)
    logger.info("Fetched %d Conditional Access policies.", len(policies))
    return policies


def get_named_locations(access_token: str) -> list[dict]:
    """
    Fetch all named locations (trusted IPs / country-based).
    Returns raw Graph API objects.
    """
    url = f"{_GRAPH_BASE}/identity/conditionalAccess/namedLocations"
    locations = _get(url, access_token)
    logger.info("Fetched %d named locations.", len(locations))
    return locations


def get_sensitivity_labels(access_token: str) -> list[dict]:
    """
    Fetch sensitivity labels from the tenant.
    Returns raw Graph API objects.
    """
    url = f"{_GRAPH_BASE}/security/informationProtection/sensitivityLabels"
    try:
        labels = _get(url, access_token)
        logger.info("Fetched %d sensitivity labels.", len(labels))
        return labels
    except httpx.HTTPStatusError as exc:
        # Some tenants don't have this permission configured
        if exc.response.status_code in (403, 404):
            logger.warning(
                "Sensitivity labels unavailable (status %d). "
                "Ensure InformationProtectionPolicy.Read.All is granted.",
                exc.response.status_code,
            )
            return []
        raise


def pull_all(access_token: str) -> dict[str, list[dict]]:
    """
    Pull all supported policy types in one call.

    Returns
    -------
    {
        "conditional_access": [...],
        "named_locations":    [...],
        "sensitivity_labels": [...],
    }
    """
    return {
        "conditional_access": get_conditional_access_policies(access_token),
        "named_locations":    get_named_locations(access_token),
        "sensitivity_labels": get_sensitivity_labels(access_token),
    }
