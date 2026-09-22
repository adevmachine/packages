import json
import os
import subprocess
import sys
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import parse_qs, urlparse

PROVIDER = os.path.join(os.path.dirname(__file__), "..", "bin", "provider")


class FakeCloudflare(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def _body(self):
        length = int(self.headers.get("Content-Length", 0))
        if length == 0:
            return None
        return json.loads(self.rfile.read(length))

    def _reply(self, status, payload):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _envelope(self, result):
        return {"success": True, "errors": [], "messages": [], "result": result}

    def do_GET(self):
        parsed = urlparse(self.path)
        qs = parse_qs(parsed.query)
        self.server.requests.append(("GET", parsed.path, qs, None))

        if self.server.force_failure:
            self._reply(200, {"success": False, "errors": [{"code": 1, "message": "something broke"}], "result": None})
            return

        if parsed.path == "/zones":
            name = qs.get("name", [None])[0]
            matches = [z for z in self.server.zones if z["name"] == name]
            self._reply(200, self._envelope(matches))
            return

        if parsed.path.endswith("/dns_records"):
            zone_id = parsed.path.split("/")[2]
            records = [r for r in self.server.records if r["zone_id"] == zone_id]
            rtype = qs.get("type", [None])[0]
            if rtype:
                records = [r for r in records if r["type"] == rtype]
            exact = qs.get("name.exact", [None])[0]
            if exact:
                records = [r for r in records if r["name"] == exact]
            self._reply(200, self._envelope(records))
            return

        self._reply(404, {"success": False, "errors": [{"code": 7003, "message": "not found"}]})

    def do_POST(self):
        body = self._body()
        parsed = urlparse(self.path)
        self.server.requests.append(("POST", parsed.path, None, body))
        zone_id = parsed.path.split("/")[2]
        record = dict(body)
        record["id"] = uuid.uuid4().hex
        record["zone_id"] = zone_id
        self.server.records.append(record)
        self._reply(200, self._envelope(record))

    def do_PATCH(self):
        body = self._body()
        parsed = urlparse(self.path)
        self.server.requests.append(("PATCH", parsed.path, None, body))
        record_id = parsed.path.rsplit("/", 1)[1]
        for record in self.server.records:
            if record["id"] == record_id:
                record.update(body)
                self._reply(200, self._envelope(record))
                return
        self._reply(404, {"success": False, "errors": [{"code": 81044, "message": "record not found"}]})

    def do_PUT(self):
        body = self._body()
        parsed = urlparse(self.path)
        self.server.requests.append(("PUT", parsed.path, None, body))
        self._reply(400, {"success": False, "errors": [{"code": 0, "message": "PUT is not expected"}]})

    def do_DELETE(self):
        parsed = urlparse(self.path)
        self.server.requests.append(("DELETE", parsed.path, None, None))
        record_id = parsed.path.rsplit("/", 1)[1]
        before = len(self.server.records)
        self.server.records = [r for r in self.server.records if r["id"] != record_id]
        if len(self.server.records) == before:
            self._reply(404, {"success": False, "errors": [{"code": 81044, "message": "record not found"}]})
            return
        self._reply(200, self._envelope({"id": record_id}))


class FakeServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zones = []
        self.records = []
        self.requests = []
        self.force_failure = False


class ProviderTest(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer(("127.0.0.1", 0), FakeCloudflare)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        self.base_url = "http://127.0.0.1:%d" % self.server.server_port
        self.server.zones = [{"id": "zone-id-0123456789abcdef", "name": "example.com"}]

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()

    def run_provider(self, args, stdin=""):
        env = dict(os.environ)
        env["CLOUDFLARE_API_TOKEN"] = "cf_test_token"
        env["DEVMACHINE_DNS_BASE"] = self.base_url
        return subprocess.run(
            [sys.executable, PROVIDER] + args,
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
        )

    def add_record(self, name, rtype, content, ttl=3600, proxied=False):
        record = {
            "id": uuid.uuid4().hex,
            "zone_id": self.server.zones[0]["id"],
            "name": name,
            "type": rtype,
            "content": content,
            "ttl": ttl,
            "proxied": proxied,
        }
        self.server.records.append(record)
        return record

    def test_the_zone_id_is_looked_up_once(self):
        self.add_record("www.example.com", "A", "198.51.100.10")
        result = self.run_provider(["list", "example.com"])
        self.assertEqual(result.returncode, 0)
        zone_lookups = [r for r in self.server.requests if r[1] == "/zones"]
        self.assertEqual(len(zone_lookups), 1)

    def test_an_empty_zone_list_is_reported_as_zone_not_found(self):
        # A name with no matching zone is a 200 with an empty result, not a 404.
        self.server.zones = []
        result = self.run_provider(["list", "example.com"])
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertEqual(out["error"]["kind"], "zone_not_found")

    def test_success_false_is_a_failure_even_with_a_200(self):
        # The v4 envelope's success flag is the source of truth, not the status code.
        self.server.force_failure = True
        result = self.run_provider(["list", "example.com"])
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertIn(out["error"]["kind"], {"invalid_record", "zone_not_found"})

    def test_a_full_name_becomes_a_label_and_back(self):
        self.add_record("www.example.com", "A", "198.51.100.10")
        self.add_record("example.com", "A", "198.51.100.20")
        result = self.run_provider(["list", "example.com"])
        out = json.loads(result.stdout)
        names = {r["name"]: r["value"] for r in out["records"]}
        self.assertEqual(names["www"], "198.51.100.10")
        self.assertEqual(names["@"], "198.51.100.20")

    def test_a_name_that_merely_ends_in_the_zone_is_not_truncated(self):
        self.add_record("notexample.com", "A", "198.51.100.30")
        result = self.run_provider(["list", "example.com"])
        out = json.loads(result.stdout)
        names = [r["name"] for r in out["records"]]
        self.assertIn("notexample.com", names)

    def test_upsert_creates_with_proxying_off(self):
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        posts = [r for r in self.server.requests if r[0] == "POST"]
        self.assertEqual(len(posts), 1)
        self.assertIs(posts[0][3]["proxied"], False)
        self.assertEqual(posts[0][3]["name"], "www.example.com")

    def test_upsert_patches_rather_than_puts(self):
        self.add_record("www.example.com", "A", "198.51.100.10", ttl=300)
        record = {"name": "www", "type": "A", "value": "198.51.100.20", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        patches = [r for r in self.server.requests if r[0] == "PATCH"]
        puts = [r for r in self.server.requests if r[0] == "PUT"]
        self.assertEqual(len(patches), 1)
        self.assertEqual(puts, [])
        self.assertEqual(patches[0][3]["content"], "198.51.100.20")

    def test_upsert_does_nothing_when_already_right(self):
        self.add_record("www.example.com", "A", "198.51.100.10", ttl=300)
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        writes = [r for r in self.server.requests if r[0] in ("POST", "PATCH", "PUT", "DELETE")]
        self.assertEqual(writes, [])

    def test_upsert_refuses_to_guess_between_several_values(self):
        self.add_record("www.example.com", "A", "198.51.100.10")
        self.add_record("www.example.com", "A", "198.51.100.11")
        record = {"name": "www", "type": "A", "value": "198.51.100.12", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertEqual(out["error"]["kind"], "ambiguous")
        writes = [r for r in self.server.requests if r[0] in ("POST", "PATCH", "PUT", "DELETE")]
        self.assertEqual(writes, [])

    def test_delete_removes_the_matching_value_only(self):
        self.add_record("www.example.com", "A", "198.51.100.10")
        self.add_record("www.example.com", "A", "198.51.100.11")
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 0}
        result = self.run_provider(["delete", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        remaining = [r["content"] for r in self.server.records]
        self.assertEqual(remaining, ["198.51.100.11"])

    def test_per_page_is_always_sent(self):
        self.add_record("www.example.com", "A", "198.51.100.10")
        self.run_provider(["list", "example.com"])
        gets = [r for r in self.server.requests if r[0] == "GET"]
        for _, _, qs, _ in gets:
            self.assertIn("per_page", qs)


if __name__ == "__main__":
    unittest.main()
