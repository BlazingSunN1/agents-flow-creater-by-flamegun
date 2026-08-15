from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from browser_url_validation import is_http_browser_url


class BrowserUrlValidationTests(unittest.TestCase):
    def test_http_and_https_urls_are_accepted(self) -> None:
        self.assertTrue(is_http_browser_url("http://127.0.0.1:4173/index.html#module"))
        self.assertTrue(is_http_browser_url("https://example.test/app"))

    def test_file_credentials_and_nonstandard_urls_are_rejected(self) -> None:
        for value in (
            "file:///tmp/index.html",
            "ftp://example.test/index.html",
            "javascript:alert(1)",
            "http://user:password@127.0.0.1:4173/",
            "http:///missing-host",
            True,
        ):
            with self.subTest(value=value):
                self.assertFalse(is_http_browser_url(value))


if __name__ == "__main__":
    unittest.main()
