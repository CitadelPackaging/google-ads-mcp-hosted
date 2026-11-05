"""Tests for the read-only Search Console tools (CitadelPackaging fork)."""

import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools import search_console


def _response(payload):
    """Builds a fake urlopen() context manager returning JSON."""
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    return resp


@patch("ads_mcp.google_rest.access_token", return_value="test-token")
@patch("urllib.request.urlopen")
class TestSearchConsoleTools(unittest.TestCase):
    """Checks the requests each tool sends and how it parses replies."""

    def _sent(self, mock_urlopen):
        req = mock_urlopen.call_args.args[0]
        body = json.loads(req.data) if req.data else None
        return req, body

    def test_list_sites(self, mock_urlopen, _):
        mock_urlopen.return_value = _response(
            {"siteEntry": [{"siteUrl": "sc-domain:example.com"}]}
        )
        self.assertEqual(
            search_console.list_sites(), [{"siteUrl": "sc-domain:example.com"}]
        )
        req, body = self._sent(mock_urlopen)
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(
            req.full_url, "https://www.googleapis.com/webmasters/v3/sites"
        )
        self.assertEqual(req.get_header("Authorization"), "Bearer test-token")
        self.assertIsNone(body)

    def test_list_sites_empty(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({})
        self.assertEqual(search_console.list_sites(), [])

    def test_query_encodes_site_and_builds_body(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({"rows": []})
        search_console.query_search_analytics(
            site_url="https://www.example.com/",
            start_date="2026-10-01",
            end_date="2026-10-31",
            dimensions=["query", "page"],
            filters=[{"dimension": "country", "expression": "usa"}],
            row_limit=50,
        )
        req, body = self._sent(mock_urlopen)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(
            req.full_url,
            "https://www.googleapis.com/webmasters/v3/sites/"
            "https%3A%2F%2Fwww.example.com%2F/searchAnalytics/query",
        )
        self.assertEqual(body["dimensions"], ["query", "page"])
        self.assertEqual(body["rowLimit"], 50)
        self.assertEqual(body["type"], "web")
        self.assertEqual(
            body["dimensionFilterGroups"],
            [
                {
                    "groupType": "and",
                    "filters": [
                        {
                            "dimension": "country",
                            "operator": "equals",
                            "expression": "usa",
                        }
                    ],
                }
            ],
        )

    def test_query_omits_empty_dimensions_and_filters(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({})
        search_console.query_search_analytics(
            "sc-domain:example.com", "2026-10-01", "2026-10-31"
        )
        req, body = self._sent(mock_urlopen)
        self.assertIn("sc-domain%3Aexample.com", req.full_url)
        self.assertNotIn("dimensions", body)
        self.assertNotIn("dimensionFilterGroups", body)

    def test_query_rejects_bad_input(self, mock_urlopen, _):
        bad_calls = [
            {"row_limit": 0},
            {"row_limit": 25001},
            {"start_row": -1},
            {"filters": [{"dimension": "date", "expression": "x"}]},
            {"filters": [{"dimension": "query", "operator": "like", "expression": "x"}]},
            {"filters": [{"dimension": "query", "expression": ""}]},
            {"filters": [{"dimension": "query", "expression": "x", "extra": "y"}]},
        ]
        for kwargs in bad_calls:
            with self.subTest(kwargs=kwargs), self.assertRaises(ToolError):
                search_console.query_search_analytics(
                    "sc-domain:example.com", "2026-10-01", "2026-10-31", **kwargs
                )
        mock_urlopen.assert_not_called()

    def test_list_sitemaps_with_index(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({"sitemap": [{"path": "x"}]})
        result = search_console.list_sitemaps(
            "sc-domain:example.com", "https://example.com/index.xml"
        )
        self.assertEqual(result, [{"path": "x"}])
        req, _ = self._sent(mock_urlopen)
        self.assertTrue(
            req.full_url.endswith(
                "/sites/sc-domain%3Aexample.com/sitemaps"
                "?sitemapIndex=https%3A%2F%2Fexample.com%2Findex.xml"
            )
        )

    def test_inspect_url(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({"inspectionResult": {}})
        search_console.inspect_url(
            "sc-domain:example.com", "https://example.com/page"
        )
        req, body = self._sent(mock_urlopen)
        self.assertEqual(
            req.full_url,
            "https://searchconsole.googleapis.com/v1/urlInspection/index:inspect",
        )
        self.assertEqual(
            body,
            {
                "inspectionUrl": "https://example.com/page",
                "siteUrl": "sc-domain:example.com",
                "languageCode": "en-US",
            },
        )

    def test_http_error_becomes_tool_error(self, mock_urlopen, _):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url",
            403,
            "Forbidden",
            {},
            io.BytesIO(b'{"error": {"message": "User does not have access"}}'),
        )
        with self.assertRaisesRegex(ToolError, "403: User does not have access"):
            search_console.list_sites()


class TestSearchConsoleMounting(unittest.TestCase):
    """Checks the tools are registered as read-only."""

    def test_tools_are_read_only(self):
        tools = [
            v
            for k, v in search_console.search_console_mcp.local_provider._components.items()
            if k.startswith("tool:")
        ]
        self.assertEqual(
            sorted(t.name for t in tools),
            ["inspect_url", "list_sitemaps", "list_sites", "query_search_analytics"],
        )
        for t in tools:
            self.assertTrue(t.annotations.read_only_hint, t.name)


if __name__ == "__main__":
    unittest.main()
