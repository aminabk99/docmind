"""
Policy formatter for M365Mind.

Converts raw Microsoft Graph API JSON objects into clean, readable prose
that can be chunked and embedded by backend/ingest.py.

A raw Conditional Access policy has 15+ nested fields with UUIDs and
enum strings. This module translates that into natural language so the
retrieval pipeline can surface it accurately.

Example output for a Conditional Access policy
-----------------------------------------------
Policy: Require MFA for All External Users
Status: Enabled
Last modified: 2024-11-03

Who it applies to:
  - Users: All users
  - Excluded groups: Service Accounts, Break Glass Accounts

Conditions:
  - Locations: All locations except Trusted Locations
  - Platforms: Any device platform
  - Client apps: Browser, Mobile apps and desktop clients

Access controls (Grant):
  - Require multi-factor authentication

Session controls: None configured.
"""

from __future__ import annotations

from typing import Any


# ── Helpers ──────────────────────────────────────────────────────────────────

def _list_or_none(items: list, label: str = "") -> str:
    if not items:
        return "None"
    joined = ", ".join(str(i) for i in items if i)
    return f"{label}: {joined}" if label else joined


def _yn(value: Any) -> str:
    if value is True:
        return "Yes"
    if value is False:
        return "No"
    return "Not configured"


_BUILT_IN_CONTROLS: dict[str, str] = {
    "mfa":                      "Require multi-factor authentication",
    "compliantDevice":          "Require device to be marked compliant (Intune)",
    "domainJoinedDevice":       "Require Hybrid Azure AD joined device",
    "approvedApplication":      "Require approved client app",
    "compliantApplication":     "Require app protection policy",
    "passwordChange":           "Require password change",
    "block":                    "Block access",
}

_CLIENT_APP_TYPES: dict[str, str] = {
    "browser":                  "Browser",
    "mobileAppsAndDesktopClients": "Mobile apps and desktop clients",
    "exchangeActiveSync":       "Exchange ActiveSync clients",
    "easSupported":             "Exchange ActiveSync (supported platforms)",
    "other":                    "Other clients (legacy)",
}

_PLATFORM_MAP: dict[str, str] = {
    "android": "Android",
    "iOS":     "iOS",
    "windows": "Windows",
    "macOS":   "macOS",
    "linux":   "Linux",
    "all":     "All platforms",
}


# ── Conditional Access ────────────────────────────────────────────────────────

def format_conditional_access_policy(policy: dict) -> str:
    lines: list[str] = []

    name    = policy.get("displayName", "Unnamed Policy")
    state   = policy.get("state", "unknown").capitalize()
    created = (policy.get("createdDateTime", "") or "")[:10]
    modified = (policy.get("modifiedDateTime", "") or "")[:10]

    lines.append(f"Policy: {name}")
    lines.append(f"Status: {state}")
    if created:
        lines.append(f"Created: {created}")
    if modified:
        lines.append(f"Last modified: {modified}")

    # ── Conditions ────────────────────────────────────────────────────────
    cond = policy.get("conditions", {}) or {}
    lines.append("\nWho it applies to:")

    users = cond.get("users", {}) or {}
    inc_users  = users.get("includeUsers",  []) or []
    exc_users  = users.get("excludeUsers",  []) or []
    inc_groups = users.get("includeGroups", []) or []
    exc_groups = users.get("excludeGroups", []) or []
    inc_roles  = users.get("includeRoles",  []) or []
    exc_roles  = users.get("excludeRoles",  []) or []

    if "All" in inc_users:
        lines.append("  - Users: All users")
    elif inc_users:
        lines.append(f"  - Users (included): {', '.join(inc_users)}")

    if inc_groups:
        lines.append(f"  - Included groups: {len(inc_groups)} group(s)")
    if exc_groups:
        lines.append(f"  - Excluded groups: {len(exc_groups)} group(s)")
    if inc_roles:
        lines.append(f"  - Included roles: {len(inc_roles)} role(s)")
    if exc_roles:
        lines.append(f"  - Excluded roles: {len(exc_roles)} role(s)")
    if exc_users:
        lines.append(f"  - Excluded users: {len(exc_users)} user(s)")

    lines.append("\nConditions:")

    # Locations
    locs = cond.get("locations", {}) or {}
    inc_locs = locs.get("includeLocations", []) or []
    exc_locs = locs.get("excludeLocations", []) or []
    if inc_locs or exc_locs:
        inc_str = "All locations" if "All" in inc_locs else f"{len(inc_locs)} location(s)"
        exc_str = ""
        if "AllTrusted" in exc_locs:
            exc_str = " except Trusted Locations"
        elif exc_locs:
            exc_str = f" except {len(exc_locs)} location(s)"
        lines.append(f"  - Locations: {inc_str}{exc_str}")

    # Platforms
    plats = cond.get("platforms", {}) or {}
    if plats:
        inc_p = plats.get("includePlatforms", []) or []
        exc_p = plats.get("excludePlatforms", []) or []
        mapped = [_PLATFORM_MAP.get(p, p) for p in inc_p]
        plat_str = ", ".join(mapped) if mapped else "Any platform"
        if exc_p:
            exc_mapped = [_PLATFORM_MAP.get(p, p) for p in exc_p]
            plat_str += f" except {', '.join(exc_mapped)}"
        lines.append(f"  - Platforms: {plat_str}")

    # Client apps
    apps = cond.get("clientAppTypes", []) or []
    if apps:
        mapped_apps = [_CLIENT_APP_TYPES.get(a, a) for a in apps]
        lines.append(f"  - Client apps: {', '.join(mapped_apps)}")

    # Sign-in risk
    risk = cond.get("signInRiskLevels", []) or []
    if risk:
        lines.append(f"  - Sign-in risk levels: {', '.join(risk)}")

    # User risk
    user_risk = cond.get("userRiskLevels", []) or []
    if user_risk:
        lines.append(f"  - User risk levels: {', '.join(user_risk)}")

    # ── Grant controls ────────────────────────────────────────────────────
    grant = policy.get("grantControls", {}) or {}
    if grant:
        lines.append("\nAccess controls (Grant):")
        built_in = grant.get("builtInControls", []) or []
        operator = grant.get("operator", "OR")
        if built_in:
            for ctrl in built_in:
                lines.append(f"  - {_BUILT_IN_CONTROLS.get(ctrl, ctrl)}")
        if len(built_in) > 1:
            lines.append(f"  (Controls applied with {operator} logic)")
        custom_auth = grant.get("customAuthenticationFactors", []) or []
        if custom_auth:
            lines.append(f"  - Custom auth factors: {', '.join(custom_auth)}")
    else:
        lines.append("\nAccess controls (Grant): Not configured.")

    # ── Session controls ──────────────────────────────────────────────────
    session = policy.get("sessionControls", {}) or {}
    if session:
        lines.append("\nSession controls:")
        sign_in_freq = session.get("signInFrequency", {}) or {}
        if sign_in_freq.get("isEnabled"):
            val  = sign_in_freq.get("value", "")
            unit = sign_in_freq.get("type", "")
            lines.append(f"  - Sign-in frequency: every {val} {unit}")
        persistent = session.get("persistentBrowser", {}) or {}
        if persistent.get("isEnabled"):
            lines.append(f"  - Persistent browser: {persistent.get('mode', 'configured')}")
        cloud_app_sec = session.get("cloudAppSecurity", {}) or {}
        if cloud_app_sec.get("isEnabled"):
            lines.append(f"  - Cloud App Security: {cloud_app_sec.get('cloudAppSecurityType', 'enabled')}")
    else:
        lines.append("\nSession controls: None configured.")

    return "\n".join(lines)


# ── Named Locations ───────────────────────────────────────────────────────────

def format_named_location(location: dict) -> str:
    lines: list[str] = []

    name     = location.get("displayName", "Unnamed Location")
    odata    = location.get("@odata.type", "")
    trusted  = location.get("isTrusted", False)
    created  = (location.get("createdDateTime", "") or "")[:10]
    modified = (location.get("modifiedDateTime", "") or "")[:10]

    lines.append(f"Named Location: {name}")
    lines.append(f"Trusted: {'Yes' if trusted else 'No'}")
    if created:
        lines.append(f"Created: {created}")
    if modified:
        lines.append(f"Last modified: {modified}")

    if "ipNamedLocation" in odata or "ipRanges" in location:
        ip_ranges = location.get("ipRanges", []) or []
        lines.append(f"\nType: IP-based location")
        lines.append(f"IP ranges defined: {len(ip_ranges)}")
        for r in ip_ranges[:5]:   # show first 5 to avoid huge chunks
            lines.append(f"  - {r.get('cidrAddress', r)}")
        if len(ip_ranges) > 5:
            lines.append(f"  ... and {len(ip_ranges) - 5} more ranges")

    elif "countryNamedLocation" in odata or "countriesAndRegions" in location:
        countries = location.get("countriesAndRegions", []) or []
        lines.append(f"\nType: Country/region-based location")
        lines.append(f"Countries included: {', '.join(countries) if countries else 'None'}")
        inc_unknown = location.get("includeUnknownCountriesAndRegions", False)
        lines.append(f"Include unknown/unresolvable countries: {'Yes' if inc_unknown else 'No'}")

    return "\n".join(lines)


# ── Sensitivity Labels ────────────────────────────────────────────────────────

def format_sensitivity_label(label: dict) -> str:
    lines: list[str] = []

    name        = label.get("name", "Unnamed Label")
    description = label.get("description", "")
    sensitivity = label.get("sensitivity", 0)
    tooltip     = label.get("tooltip", "")
    is_active   = label.get("isActive", True)
    is_parent   = label.get("isParent", False)

    lines.append(f"Sensitivity Label: {name}")
    if description:
        lines.append(f"Description: {description}")
    if tooltip:
        lines.append(f"Tooltip: {tooltip}")
    lines.append(f"Sensitivity order: {sensitivity}")
    lines.append(f"Active: {'Yes' if is_active else 'No'}")
    if is_parent:
        lines.append("Type: Parent label (contains sublabels)")

    # Content markings
    markings = label.get("contentMarkings", []) or []
    if markings:
        lines.append("\nContent markings:")
        for m in markings:
            mtype = m.get("@odata.type", "").replace("#microsoft.graph.", "")
            lines.append(f"  - {mtype}")

    # Encryption
    encryption = label.get("encryption", {}) or {}
    if encryption:
        lines.append(f"\nEncryption: Configured")
        if encryption.get("templateId"):
            lines.append(f"  Template ID: {encryption['templateId']}")

    return "\n".join(lines)


# ── Dispatcher ────────────────────────────────────────────────────────────────

def format_policy(policy_type: str, obj: dict) -> tuple[str, str]:
    """
    Format a Graph API object into (display_name, formatted_text).

    Parameters
    ----------
    policy_type : "conditional_access" | "named_location" | "sensitivity_label"
    obj         : raw Graph API JSON dict

    Returns
    -------
    (display_name, text) — ready to pass to ingest_text()
    """
    if policy_type == "conditional_access":
        name = obj.get("displayName", "Unnamed Policy")
        text = format_conditional_access_policy(obj)
    elif policy_type == "named_location":
        name = obj.get("displayName", "Unnamed Location")
        text = format_named_location(obj)
    elif policy_type == "sensitivity_label":
        name = obj.get("name", "Unnamed Label")
        text = format_sensitivity_label(obj)
    else:
        name = obj.get("displayName", obj.get("name", "Unknown"))
        text = str(obj)

    return name, text
