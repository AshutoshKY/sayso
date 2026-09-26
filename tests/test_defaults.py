import unittest

from opener.defaults import default_browser_id


CATALOG = {
    "safari": {"bundle": "com.apple.Safari"},
    "chrome": {"bundle": "com.google.Chrome"},
    "brave": {"bundle": "com.brave.Browser"},
    "arc": {"bundle": "company.thebrowser.Browser"},
}


class DefaultBrowserTests(unittest.TestCase):
    def test_maps_http_handler_bundle_to_catalog_id(self):
        handlers = [
            {"scheme": "mailto", "bundle": "com.apple.mail"},
            {"scheme": "http", "bundle": "com.brave.Browser"},
            {"scheme": "https", "bundle": "com.brave.Browser"},
        ]
        self.assertEqual(default_browser_id(handlers, CATALOG), "brave")

    def test_falls_back_to_safari_when_handler_unknown(self):
        handlers = [{"scheme": "http", "bundle": "org.mozilla.firefox"}]
        self.assertEqual(default_browser_id(handlers, CATALOG), "safari")

    def test_falls_back_to_safari_when_empty(self):
        self.assertEqual(default_browser_id([], CATALOG), "safari")


if __name__ == "__main__":
    unittest.main()
