"""
Microsoft OAuth2 authentication for M365Mind.

Flow
----
1. Frontend calls GET /auth-url  → returns the Microsoft login URL
2. User clicks the link, signs in with their Microsoft 365 work account
3. Microsoft redirects to GET /callback?code=...
4. Backend exchanges the code for an access token via MSAL
5. Token stored in _token_store keyed by a random session ID
6. Callback redirects to http://localhost:8501?m365_connected=true&sid=<session_id>
7. Frontend polls GET /auth-status?sid=<session_id> to confirm connection

Requires: pip install msal
"""

from __future__ import annotations

import logging
import secrets
from typing import Optional

logger = logging.getLogger(__name__)

# In-memory token store: {session_id: token_dict}
# Fine for a local single-user tool; replace with persistent store for multi-user.
_token_store: dict[str, dict] = {}


def _get_msal_app():
    """Build a confidential MSAL client app from config."""
    import msal
    from backend.config import AZURE_CLIENT_ID, AZURE_TENANT_ID, AZURE_CLIENT_SECRET

    return msal.ConfidentialClientApplication(
        client_id=AZURE_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{AZURE_TENANT_ID}",
        client_credential=AZURE_CLIENT_SECRET,
    )


def get_auth_url(state: Optional[str] = None) -> str:
    """
    Generate the Microsoft login URL.

    Parameters
    ----------
    state : optional CSRF token (generated automatically if omitted)

    Returns
    -------
    URL string — open this in the browser to start the login flow.
    """
    from backend.config import AZURE_REDIRECT_URI, GRAPH_SCOPES

    app   = _get_msal_app()
    state = state or secrets.token_urlsafe(16)

    url = app.get_authorization_request_url(
        scopes=GRAPH_SCOPES,
        redirect_uri=AZURE_REDIRECT_URI,
        state=state,
    )
    logger.info("Auth URL generated.")
    return url


def exchange_code(code: str) -> str:
    """
    Exchange an authorization code for an access token.

    Returns
    -------
    session_id : use this to retrieve the token later via get_token()

    Raises
    ------
    RuntimeError if MSAL returns an error.
    """
    from backend.config import AZURE_REDIRECT_URI, GRAPH_SCOPES

    app    = _get_msal_app()
    result = app.acquire_token_by_authorization_code(
        code=code,
        scopes=GRAPH_SCOPES,
        redirect_uri=AZURE_REDIRECT_URI,
    )

    if "error" in result:
        raise RuntimeError(
            f"MSAL error: {result.get('error')} — {result.get('error_description')}"
        )

    session_id = secrets.token_urlsafe(24)
    _token_store[session_id] = result
    logger.info("Token acquired and stored (session: %s...)", session_id[:8])
    return session_id


def get_token(session_id: str) -> Optional[str]:
    """
    Return the access token string for a session ID, or None if not found.
    """
    entry = _token_store.get(session_id)
    if not entry:
        return None
    return entry.get("access_token")


def is_connected(session_id: str) -> bool:
    """Return True if a valid token exists for this session."""
    return bool(get_token(session_id))


def clear_session(session_id: str) -> None:
    """Remove a session token (logout)."""
    _token_store.pop(session_id, None)
