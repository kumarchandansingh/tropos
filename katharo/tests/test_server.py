import json
import tempfile
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from katharo.server import App, handler_for


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app = App(Path(self.temp.name))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.app))
        self.app.port = self.server.server_port
        self.url = f"http://127.0.0.1:{self.app.port}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.app.pool.shutdown()
        self.app.store.db.close()
        self.temp.cleanup()

    def test_static_page_and_session(self):
        with urlopen(self.url) as response:
            self.assertIn(b"Make room", response.read())
            self.assertIn("frame-ancestors 'none'", response.headers["Content-Security-Policy"])
        with urlopen(self.url + "/api/session") as response:
            self.assertEqual(json.load(response)["token"], self.app.token)

    def test_missing_token_rejected(self):
        request = Request(
            self.url + "/api/history", data=b"{}", headers={"Content-Type": "application/json"}
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_foreign_origin_rejected_even_with_token(self):
        request = Request(
            self.url + "/api/history",
            data=b"{}",
            headers={"X-Katharo-Token": self.app.token, "Origin": "https://unrelated.example"},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 403)

    def test_approval_required(self):
        request = Request(
            self.url + "/api/execute",
            data=b'{"id":"x"}',
            headers={"X-Katharo-Token": self.app.token},
        )
        with self.assertRaises(HTTPError) as error:
            urlopen(request)
        self.assertEqual(error.exception.code, 400)


if __name__ == "__main__":
    unittest.main()
