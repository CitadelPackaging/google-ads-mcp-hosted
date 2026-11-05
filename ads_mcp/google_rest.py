"""Small JSON-over-HTTPS helper for Google REST APIs.

Added in the CitadelPackaging fork for the Search Console and Merchant
Center tools; not part of upstream google-ads-mcp. Uses only the standard
library, so it adds no dependencies.

In remote OAuth mode, the caller's Google access token from the FastMCP
OAuth proxy is used. In local stdio mode, Application Default Credentials
are used, requested with the scope the calling tool needs.
"""

import json
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict

from fastmcp.exceptions import ToolError

_TIMEOUT_SECONDS = 60


def access_token(scope: str) -> str:
    """Returns a Google access token for the current caller."""
    from fastmcp.server.dependencies import get_access_token

    token_obj = get_access_token()
    if token_obj and token_obj.token:
        return token_obj.token

    import google.auth
    import google.auth.transport.requests

    credentials, _ = google.auth.default(scopes=[scope])
    credentials.refresh(google.auth.transport.requests.Request())
    return credentials.token


def request(
    method: str,
    url: str,
    *,
    scope: str,
    api_name: str,
    body: Dict[str, Any] | None = None,
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Sends an authorized JSON request and returns the decoded response.

    Query parameters whose value is None are dropped.
    """
    if params:
        query = {k: v for k, v in params.items() if v is not None}
        if query:
            url += "?" + urllib.parse.urlencode(query)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Authorization", f"Bearer {access_token(scope)}")
    req.add_header("Accept", "application/json")
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT_SECONDS) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as ex:
        raise ToolError(format_http_error(ex, api_name)) from ex
    except urllib.error.URLError as ex:
        raise ToolError(f"{api_name} request failed: {ex.reason}") from ex
    return json.loads(raw) if raw else {}


def format_http_error(ex: urllib.error.HTTPError, api_name: str) -> str:
    """Builds a readable message from a Google API error response."""
    try:
        payload = json.loads(ex.read() or b"{}")
        message = payload.get("error", {}).get("message") or ex.reason
    except (ValueError, AttributeError):
        message = ex.reason
    return f"{api_name} API error {ex.code}: {message}"
