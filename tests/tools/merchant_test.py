"""Tests for the Merchant Center tools (CitadelPackaging fork)."""

import base64
import io
import json
import unittest
import urllib.error
from unittest.mock import MagicMock, patch

from fastmcp.exceptions import ToolError

from ads_mcp.tools import merchant

_BASE = "https://merchantapi.googleapis.com"


def _response(payload):
    resp = MagicMock()
    resp.read.return_value = json.dumps(payload).encode()
    resp.__enter__.return_value = resp
    return resp


@patch("ads_mcp.google_rest.access_token", return_value="test-token")
@patch("urllib.request.urlopen")
class TestMerchantTools(unittest.TestCase):
    """Checks the requests each tool sends."""

    def _sent(self, mock_urlopen):
        req = mock_urlopen.call_args.args[0]
        body = json.loads(req.data) if req.data else None
        return req, body

    def test_list_accounts(self, mock_urlopen, mock_token):
        mock_urlopen.return_value = _response({"accounts": []})
        merchant.list_accounts()
        req, body = self._sent(mock_urlopen)
        self.assertEqual(req.get_method(), "GET")
        self.assertEqual(req.full_url, f"{_BASE}/accounts/v1/accounts?pageSize=250")
        self.assertEqual(req.get_header("Authorization"), "Bearer test-token")
        self.assertIsNone(body)
        mock_token.assert_called_with(merchant.MERCHANT_SCOPE)

    def test_account_id_forms(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({})
        for given in ("123456", 123456, "accounts/123456", "123-456"):
            with self.subTest(given=given):
                merchant.list_data_sources(given)
                req, _ = self._sent(mock_urlopen)
                self.assertTrue(
                    req.full_url.startswith(
                        f"{_BASE}/datasources/v1/accounts/123456/dataSources"
                    )
                )
        with self.assertRaises(ToolError):
            merchant.list_data_sources("abc")

    def test_account_issues_params(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({})
        merchant.list_account_issues("42")
        req, _ = self._sent(mock_urlopen)
        self.assertEqual(
            req.full_url,
            f"{_BASE}/accounts/v1/accounts/42/issues"
            "?languageCode=en-US&timeZone=America%2FDenver&pageSize=100",
        )

    def test_status_summary_filter(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({})
        merchant.list_product_status_summary(
            "42", filter='country = "US"'
        )
        req, _ = self._sent(mock_urlopen)
        self.assertIn("/issueresolution/v1/accounts/42/aggregateProductStatuses?", req.full_url)
        self.assertIn("filter=country+%3D+%22US%22", req.full_url)

    def test_get_product_plain_and_encoded(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({})
        merchant.get_product("42", "en~US~sku-1")
        req, _ = self._sent(mock_urlopen)
        self.assertEqual(req.full_url, f"{_BASE}/products/v1/accounts/42/products/en~US~sku-1")

        merchant.get_product("42", "en~US~sku/123")
        req, _ = self._sent(mock_urlopen)
        expected = base64.urlsafe_b64encode(b"en~US~sku/123").decode().rstrip("=")
        self.assertEqual(expected, "ZW5-VVN-c2t1LzEyMw")  # Google's documented example
        self.assertTrue(req.full_url.endswith(f"/products/{expected}"))

        with self.assertRaises(ToolError):
            merchant.get_product("42", "sku123")

    def test_search_reports(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({"results": []})
        q = "SELECT offer_id, clicks FROM product_performance_view WHERE date DURING LAST_7_DAYS"
        merchant.search_reports("42", f"  {q}  ", page_size=10)
        req, body = self._sent(mock_urlopen)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(req.full_url, f"{_BASE}/reports/v1/accounts/42/reports:search")
        self.assertEqual(body, {"query": q, "pageSize": 10})

    def test_search_reports_rejects_non_select(self, mock_urlopen, _):
        for q in ("DELETE FROM product_view", "select 1; DROP x", "UPDATE product_view"):
            with self.subTest(q=q), self.assertRaises(ToolError):
                merchant.search_reports("42", q)
        with self.assertRaises(ToolError):
            merchant.search_reports("42", "SELECT offer_id FROM product_view", page_size=0)
        mock_urlopen.assert_not_called()

    def test_register_project(self, mock_urlopen, _):
        mock_urlopen.return_value = _response({})
        merchant.register_project("42")
        req, body = self._sent(mock_urlopen)
        self.assertEqual(req.get_method(), "POST")
        self.assertEqual(
            req.full_url,
            f"{_BASE}/accounts/v1/accounts/42/developerRegistration:registerGcp",
        )
        self.assertEqual(body, {})
        merchant.register_project("42", developer_email="dev@example.com")
        _, body = self._sent(mock_urlopen)
        self.assertEqual(body, {"developerEmail": "dev@example.com"})

    def test_http_error(self, mock_urlopen, _):
        mock_urlopen.side_effect = urllib.error.HTTPError(
            "url", 401, "Unauthorized", {},
            io.BytesIO(b'{"error": {"message": "GCP project is not registered"}}'),
        )
        with self.assertRaisesRegex(ToolError, "Merchant API error 401: GCP project is not registered"):
            merchant.list_accounts()


class TestMerchantAnnotations(unittest.TestCase):
    def test_only_register_project_writes(self):
        tools = {
            v.name: v
            for k, v in merchant.merchant_mcp.local_provider._components.items()
            if k.startswith("tool:")
        }
        self.assertEqual(
            sorted(tools),
            [
                "get_product",
                "list_account_issues",
                "list_accounts",
                "list_data_sources",
                "list_product_status_summary",
                "list_products",
                "register_project",
                "search_reports",
            ],
        )
        for name, tool in tools.items():
            self.assertEqual(tool.annotations.read_only_hint, name != "register_project", name)
        self.assertFalse(tools["register_project"].annotations.destructive_hint)


if __name__ == "__main__":
    unittest.main()
