from __future__ import annotations

import http.client
import unittest
from unittest.mock import MagicMock, patch

from browser_page_validation import _http_response_hash


class BrowserPageValidationTests(unittest.TestCase):
    def test_truncated_http_response_fails_closed(self) -> None:
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.geturl.return_value = "http://127.0.0.1:4173/index.html"
        response.read.side_effect = http.client.IncompleteRead(b"partial", 100)
        with patch("browser_page_validation.urlopen", return_value=response):
            self.assertIsNone(_http_response_hash("http://127.0.0.1:4173/index.html"))


if __name__ == "__main__":
    unittest.main()
