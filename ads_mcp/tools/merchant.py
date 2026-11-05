"""Google Merchant Center tools (Merchant API v1).

Added in the CitadelPackaging fork; not part of upstream google-ads-mcp.

Google offers only one Merchant API scope (`content`), and it allows both
reading and writing. These tools limit themselves to reads, apart from
`register_project`, a one-time setup call that links this server's Google
Cloud project to a Merchant Center account. It never touches products,
feeds or settings.

Authentication and HTTP handling live in ads_mcp.google_rest.
"""

import base64
import re
from typing import Any, Dict

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ads_mcp import google_rest

merchant_mcp = FastMCP("merchant")

MERCHANT_SCOPE = "https://www.googleapis.com/auth/content"
_BASE = "https://merchantapi.googleapis.com"
_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)
_SAFE_PRODUCT_ID = re.compile(r"[A-Za-z0-9._~-]+")
# Statements that would make a report query anything other than a read.
_NON_SELECT = re.compile(
    r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|DROP|ALTER)\b", re.IGNORECASE
)


def _request(
    method: str,
    url: str,
    body: Dict[str, Any] | None = None,
    params: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """Sends an authorized Merchant API request."""
    return google_rest.request(
        method,
        url,
        scope=MERCHANT_SCOPE,
        api_name="Merchant",
        body=body,
        params=params,
    )


def _account(account_id: str | int) -> str:
    """Returns 'accounts/{id}', accepting either form and stripping punctuation."""
    raw = str(account_id).strip().removeprefix("accounts/")
    digits = re.sub(r"\D", "", raw)
    if not digits:
        raise ToolError("account_id must be a numeric Merchant Center ID.")
    return f"accounts/{digits}"


def _page_size(value: int, maximum: int) -> int:
    if not 1 <= value <= maximum:
        raise ToolError(f"page_size must be between 1 and {maximum}.")
    return value


def _product_segment(product_id: str) -> str:
    """Builds the product path segment, base64url-encoding unusual IDs.

    product_id is "contentLanguage~feedLabel~offerId", for example
    "en~US~sku123". IDs containing characters that are unsafe in a URL path
    (such as "/") are sent in the API's unpadded base64url form.
    """
    product_id = product_id.strip()
    if product_id.count("~") < 2:
        raise ToolError(
            'product_id must look like "contentLanguage~feedLabel~offerId", '
            'e.g. "en~US~sku123" (use the name from list_products).'
        )
    if _SAFE_PRODUCT_ID.fullmatch(product_id):
        return product_id
    encoded = base64.urlsafe_b64encode(product_id.encode("utf-8"))
    return encoded.decode("ascii").rstrip("=")


@merchant_mcp.tool(annotations=_READ_ONLY)
def list_accounts(
    page_size: int = 250, page_token: str | None = None
) -> Dict[str, Any]:
    """Lists the Merchant Center accounts the signed-in user can access.

    Use this first to find the account_id for the other tools.

    Returns:
        {"accounts": [...], "nextPageToken": ...}. Each account's "name" is
        "accounts/{id}" and "accountName" is its display name.
    """
    return _request(
        "GET",
        f"{_BASE}/accounts/v1/accounts",
        params={"pageSize": _page_size(page_size, 500), "pageToken": page_token},
    )


@merchant_mcp.tool(annotations=_READ_ONLY)
def list_account_issues(
    account_id: str,
    language_code: str = "en-US",
    time_zone: str = "America/Denver",
    page_size: int = 100,
    page_token: str | None = None,
) -> Dict[str, Any]:
    """Lists account-level issues (policy, verification, shipping and so on).

    Args:
        account_id: Merchant Center account ID from list_accounts.
        language_code: Language for issue text.
        time_zone: IANA time zone for times in issue text.
    """
    return _request(
        "GET",
        f"{_BASE}/accounts/v1/{_account(account_id)}/issues",
        params={
            "languageCode": language_code,
            "timeZone": time_zone,
            "pageSize": _page_size(page_size, 100),
            "pageToken": page_token,
        },
    )


@merchant_mcp.tool(annotations=_READ_ONLY)
def list_product_status_summary(
    account_id: str,
    filter: str | None = None,
    page_size: int = 250,
    page_token: str | None = None,
) -> Dict[str, Any]:
    """Summarizes product approval counts and the most common product issues.

    Args:
        account_id: Merchant Center account ID from list_accounts.
        filter: Optional, e.g. 'reportingContext = "SHOPPING_ADS" AND
            country = "US"'. Only reportingContext and country are supported.

    Returns:
        aggregateProductStatuses: per reporting context and country, the
        counts of approved, pending and disapproved products, plus issues
        with the number of products each affects.
    """
    return _request(
        "GET",
        f"{_BASE}/issueresolution/v1/{_account(account_id)}/aggregateProductStatuses",
        params={
            "filter": filter,
            "pageSize": _page_size(page_size, 250),
            "pageToken": page_token,
        },
    )


@merchant_mcp.tool(annotations=_READ_ONLY)
def list_products(
    account_id: str, page_size: int = 50, page_token: str | None = None
) -> Dict[str, Any]:
    """Lists processed products with their attributes and status.

    Each product includes productStatus with destinationStatuses
    (approved, pending and disapproved countries) and itemLevelIssues.
    To find problem products across a large catalog, prefer
    list_product_status_summary or search_reports on product_view.

    Args:
        account_id: Merchant Center account ID from list_accounts.
        page_size: 1 to 1000. Products are large, so keep this small.
        page_token: nextPageToken from the previous call.
    """
    return _request(
        "GET",
        f"{_BASE}/products/v1/{_account(account_id)}/products",
        params={"pageSize": _page_size(page_size, 1000), "pageToken": page_token},
    )


@merchant_mcp.tool(annotations=_READ_ONLY)
def get_product(account_id: str, product_id: str) -> Dict[str, Any]:
    """Gets one processed product, including its status and issues.

    Args:
        account_id: Merchant Center account ID from list_accounts.
        product_id: "contentLanguage~feedLabel~offerId", e.g. "en~US~sku123",
            as in the last part of a product "name" from list_products.
    """
    segment = _product_segment(product_id)
    return _request(
        "GET", f"{_BASE}/products/v1/{_account(account_id)}/products/{segment}"
    )


@merchant_mcp.tool(annotations=_READ_ONLY)
def list_data_sources(
    account_id: str, page_size: int = 100, page_token: str | None = None
) -> Dict[str, Any]:
    """Lists the account's data sources (feeds), with their type and inputs.

    Args:
        account_id: Merchant Center account ID from list_accounts.
    """
    return _request(
        "GET",
        f"{_BASE}/datasources/v1/{_account(account_id)}/dataSources",
        params={"pageSize": _page_size(page_size, 1000), "pageToken": page_token},
    )


@merchant_mcp.tool(annotations=_READ_ONLY)
def search_reports(
    account_id: str,
    query: str,
    page_size: int = 1000,
    page_token: str | None = None,
) -> Dict[str, Any]:
    """Runs a Merchant Center report query (MCQL, a read-only SQL-like language).

    Tables: product_performance_view, non_product_performance_view,
    product_view, price_competitiveness_product_view,
    price_insights_product_view, best_sellers_product_cluster_view,
    best_sellers_brand_view, competitive_visibility_competitor_view,
    competitive_visibility_top_merchant_view and
    competitive_visibility_benchmark_view.

    Syntax: SELECT fields FROM one_table [WHERE ... AND ...]
    [ORDER BY field DESC] [LIMIT n]. Field names are snake_case. WHERE
    supports AND only. Dates use the bare `date` field, e.g.
    "date BETWEEN '2026-10-01' AND '2026-10-31'" or
    "date DURING LAST_30_DAYS".

    Example: SELECT offer_id, title, clicks, impressions
             FROM product_performance_view
             WHERE date DURING LAST_7_DAYS ORDER BY clicks DESC LIMIT 20

    Args:
        account_id: Merchant Center account ID from list_accounts.
        query: The MCQL query. Only SELECT queries are accepted.
        page_size: 1 to 100000 rows.
        page_token: nextPageToken from the previous call.
    """
    text = query.strip()
    if not text.upper().startswith("SELECT") or _NON_SELECT.search(text):
        raise ToolError("Only SELECT report queries are allowed.")
    body: Dict[str, Any] = {
        "query": text,
        "pageSize": _page_size(page_size, 100000),
    }
    if page_token:
        body["pageToken"] = page_token
    return _request(
        "POST", f"{_BASE}/reports/v1/{_account(account_id)}/reports:search", body
    )


@merchant_mcp.tool(
    annotations=ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=True,
        openWorldHint=True,
    )
)
def register_project(
    account_id: str, developer_email: str | None = None
) -> Dict[str, Any]:
    """One-time setup: links this server's Google Cloud project to a Merchant Center account.

    Google blocks Merchant API calls from a project that isn't registered,
    with a 401 "GCP project ... is not registered with the merchant account"
    error. Run this once, only when the user explicitly asks. It does not
    change products, feeds or account settings. The signed-in user needs
    ADMIN access on the account.

    Args:
        account_id: Merchant Center account ID from list_accounts.
        developer_email: Optional contact email Google can use for API
            announcements. Omit to only link the project.
    """
    body: Dict[str, Any] = {}
    if developer_email:
        body["developerEmail"] = developer_email
    return _request(
        "POST",
        f"{_BASE}/accounts/v1/{_account(account_id)}/developerRegistration:registerGcp",
        body,
    )

