"""Read-only Google Search Console tools.

Added in the CitadelPackaging fork; not part of upstream google-ads-mcp.
Every tool here only reads data, using the webmasters.readonly scope.

Authentication and HTTP handling live in ads_mcp.google_rest.
"""

import urllib.parse
from typing import Any, Dict, List, Literal

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations

from ads_mcp import google_rest

search_console_mcp = FastMCP("search_console")

GSC_SCOPE = "https://www.googleapis.com/auth/webmasters.readonly"
_WEBMASTERS_BASE = "https://www.googleapis.com/webmasters/v3"
_INSPECT_URL = (
    "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect"
)
_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=True)

Dimension = Literal[
    "country", "device", "page", "query", "searchAppearance", "date", "hour"
]
FilterDimension = Literal[
    "country", "device", "page", "query", "searchAppearance"
]
FilterOperator = Literal[
    "equals",
    "notEquals",
    "contains",
    "notContains",
    "includingRegex",
    "excludingRegex",
]


def _request(
    method: str, url: str, body: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """Sends an authorized Search Console request."""
    return google_rest.request(
        method, url, scope=GSC_SCOPE, api_name="Search Console", body=body
    )


def _site_path(site_url: str) -> str:
    """URL-encodes a property for use as a path segment."""
    return urllib.parse.quote(site_url, safe="")


@search_console_mcp.tool(annotations=_READ_ONLY)
def list_sites() -> List[Dict[str, Any]]:
    """Lists the Search Console properties the signed-in user can access.

    Use this first to find the exact site_url for the other tools. URL-prefix
    properties look like "https://www.example.com/" (trailing slash included)
    and Domain properties look like "sc-domain:example.com".

    Returns:
        A list of {"siteUrl", "permissionLevel"} entries.
    """
    result = _request("GET", f"{_WEBMASTERS_BASE}/sites")
    return result.get("siteEntry", [])


@search_console_mcp.tool(annotations=_READ_ONLY)
def query_search_analytics(
    site_url: str,
    start_date: str,
    end_date: str,
    dimensions: List[Dimension] = [],
    search_type: Literal[
        "web", "discover", "googleNews", "news", "image", "video"
    ] = "web",
    filters: List[Dict[str, str]] = [],
    aggregation_type: Literal[
        "auto", "byPage", "byProperty", "byNewsShowcasePanel"
    ] = "auto",
    row_limit: int = 1000,
    start_row: int = 0,
    data_state: Literal["final", "all", "hourly_all"] = "final",
) -> Dict[str, Any]:
    """Queries Search Console performance data: clicks, impressions, CTR and position.

    Args:
        site_url: Property from list_sites, e.g. "https://www.example.com/"
            or "sc-domain:example.com".
        start_date: First day, YYYY-MM-DD, inclusive, in Pacific Time.
        end_date: Last day, YYYY-MM-DD, inclusive, in Pacific Time.
        dimensions: Grouping, in order. Rows' "keys" follow this order.
        search_type: Which search results to report on.
        filters: Each filter is {"dimension", "operator", "expression"}, and
            all filters must match. dimension is one of country (3-letter
            ISO code, e.g. "usa"), device (DESKTOP, MOBILE or TABLET), page,
            query or searchAppearance. operator is one of equals (default),
            notEquals, contains, notContains, includingRegex or
            excludingRegex (RE2 syntax).
        aggregation_type: Use "auto" when grouping or filtering by page.
        row_limit: 1 to 25000 rows.
        start_row: Zero-based offset, for paging with row_limit.
        data_state: "final" (default) excludes the most recent, still
            changing data; "all" includes it; "hourly_all" is for the hour
            dimension.

    Returns:
        The API response, with "rows" of {keys, clicks, impressions, ctr,
        position}. ctr is a fraction from 0 to 1. Results are the top rows
        only and are not guaranteed to include all data.
    """
    if not 1 <= row_limit <= 25000:
        raise ToolError("row_limit must be between 1 and 25000.")
    if start_row < 0:
        raise ToolError("start_row must be zero or greater.")

    body: Dict[str, Any] = {
        "startDate": start_date,
        "endDate": end_date,
        "type": search_type,
        "aggregationType": aggregation_type,
        "rowLimit": row_limit,
        "startRow": start_row,
        "dataState": data_state,
    }
    if dimensions:
        body["dimensions"] = list(dimensions)
    if filters:
        body["dimensionFilterGroups"] = [
            {"groupType": "and", "filters": _validate_filters(filters)}
        ]

    url = f"{_WEBMASTERS_BASE}/sites/{_site_path(site_url)}/searchAnalytics/query"
    return _request("POST", url, body)


def _validate_filters(filters: List[Dict[str, str]]) -> List[Dict[str, str]]:
    """Checks filter dicts and fills in the default operator."""
    dimensions = set(FilterDimension.__args__)
    operators = set(FilterOperator.__args__)
    cleaned = []
    for f in filters:
        unknown = set(f) - {"dimension", "operator", "expression"}
        if unknown:
            raise ToolError(f"Unknown filter keys: {sorted(unknown)}")
        dimension = f.get("dimension")
        operator = f.get("operator", "equals")
        expression = f.get("expression")
        if dimension not in dimensions:
            raise ToolError(
                f"Filter dimension must be one of {sorted(dimensions)}."
            )
        if operator not in operators:
            raise ToolError(
                f"Filter operator must be one of {sorted(operators)}."
            )
        if not expression:
            raise ToolError("Each filter needs a non-empty expression.")
        cleaned.append(
            {
                "dimension": dimension,
                "operator": operator,
                "expression": expression,
            }
        )
    return cleaned


@search_console_mcp.tool(annotations=_READ_ONLY)
def list_sitemaps(
    site_url: str, sitemap_index: str | None = None
) -> List[Dict[str, Any]]:
    """Lists sitemaps submitted for a property, with their status and errors.

    Args:
        site_url: Property from list_sites.
        sitemap_index: Optional sitemap index URL, to list only its children.

    Returns:
        A list of sitemap entries (path, lastSubmitted, lastDownloaded,
        isPending, warnings, errors, contents).
    """
    url = f"{_WEBMASTERS_BASE}/sites/{_site_path(site_url)}/sitemaps"
    if sitemap_index:
        url += "?" + urllib.parse.urlencode({"sitemapIndex": sitemap_index})
    return _request("GET", url).get("sitemap", [])


@search_console_mcp.tool(annotations=_READ_ONLY)
def inspect_url(
    site_url: str, inspection_url: str, language_code: str = "en-US"
) -> Dict[str, Any]:
    """Returns Google's index status for one URL, as in Search Console's URL Inspection.

    This reads Google's stored data only. It does not request indexing.

    Args:
        site_url: Property from list_sites. The URL must belong to it.
        inspection_url: The full URL to inspect.
        language_code: Language for issue messages, e.g. "en-US".

    Returns:
        The inspection result: index status, crawl details, canonical URLs,
        mobile usability and rich results.
    """
    body = {
        "inspectionUrl": inspection_url,
        "siteUrl": site_url,
        "languageCode": language_code,
    }
    return _request("POST", _INSPECT_URL, body)
