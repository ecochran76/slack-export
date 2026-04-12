from __future__ import annotations

import threading
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from slack_mirror.sync.downloads import download_with_retries


class _DownloadFixtureHandler(BaseHTTPRequestHandler):
    payload = b""
    content_type = "application/octet-stream"

    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", self.content_type)
        self.send_header("Content-Length", str(len(self.payload)))
        self.end_headers()
        self.wfile.write(self.payload)

    def log_message(self, format: str, *args) -> None:  # noqa: A003
        return


class DownloadHelpersTests(unittest.TestCase):
    def test_download_with_retries_writes_binary_file(self) -> None:
        _DownloadFixtureHandler.payload = b"\x89PNG\r\n\x1a\npng"
        _DownloadFixtureHandler.content_type = "image/png"
        server = ThreadingHTTPServer(("127.0.0.1", 0), _DownloadFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                dest = Path(tmpdir) / "image.png"
                ok, checksum = download_with_retries(
                    f"http://127.0.0.1:{server.server_port}/image.png",
                    "xoxp-test-token",
                    dest,
                    retries=1,
                )
                self.assertTrue(ok)
                self.assertIsNotNone(checksum)
                self.assertEqual(dest.read_bytes(), _DownloadFixtureHandler.payload)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_download_with_retries_rejects_html_interstitial(self) -> None:
        _DownloadFixtureHandler.payload = b"<!DOCTYPE html><html><body>login</body></html>"
        _DownloadFixtureHandler.content_type = "text/html"
        server = ThreadingHTTPServer(("127.0.0.1", 0), _DownloadFixtureHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                dest = Path(tmpdir) / "image.png"
                ok, error = download_with_retries(
                    f"http://127.0.0.1:{server.server_port}/image.png",
                    "xoxp-test-token",
                    dest,
                    retries=1,
                )
                self.assertFalse(ok)
                self.assertIn("interstitial", str(error))
                self.assertFalse(dest.exists())
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
