import json
import os
import subprocess
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer

PROVIDER = os.path.join(os.path.dirname(__file__), "..", "bin", "provider")


class FakeHostinger(BaseHTTPRequestHandler):
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

    def do_GET(self):
        self.server.requests.append(("GET", self.path, None))
        if self.path.startswith("/api/domains/v1/portfolio"):
            self._reply(200, self.server.portfolio)
            return
        zone = self.server.zone
        if zone is None:
            self._reply(401, {"message": "Unauthenticated.", "correlation_id": "c-1"})
            return
        if self.server.not_found:
            self._reply(404, {"message": "Domain not found", "correlation_id": "c-2"})
            return
        self._reply(200, zone)

    def do_PUT(self):
        body = self._body()
        self.server.requests.append(("PUT", self.path, body))
        if self.server.rate_limited:
            self._reply(429, {"message": "Too many requests", "correlation_id": "c-3"})
            return
        for entry in body["zone"]:
            self.server.zone = self.server.zone or []
            existing = next(
                (r for r in self.server.zone if r["name"] == entry["name"] and r["type"] == entry["type"]),
                None,
            )
            if body["overwrite"] or existing is None:
                self.server.zone = [
                    r for r in self.server.zone if not (r["name"] == entry["name"] and r["type"] == entry["type"])
                ]
                self.server.zone.append(entry)
            else:
                existing["ttl"] = entry["ttl"]
                existing["records"].extend(entry["records"])
        self._reply(200, {"message": "Request accepted"})

    def do_DELETE(self):
        body = self._body()
        self.server.requests.append(("DELETE", self.path, body))
        for f in body["filters"]:
            self.server.zone = [
                r for r in self.server.zone if not (r["name"] == f["name"] and r["type"] == f["type"])
            ]
        self._reply(200, {"message": "Request accepted"})


class FakeServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.zone = []
        self.requests = []
        self.not_found = False
        self.rate_limited = False
        self.portfolio = []


class ProviderTest(unittest.TestCase):
    def setUp(self):
        self.server = FakeServer(("127.0.0.1", 0), FakeHostinger)
        self.thread = threading.Thread(target=self.server.serve_forever)
        self.thread.daemon = True
        self.thread.start()
        self.base_url = "http://127.0.0.1:%d" % self.server.server_port

    def tearDown(self):
        self.server.shutdown()
        self.thread.join()

    def run_provider(self, args, stdin=""):
        env = dict(os.environ)
        env["HOSTINGER_API_TOKEN"] = "hpat_test_token"
        env["DEVMACHINE_DNS_BASE"] = self.base_url
        result = subprocess.run(
            [sys.executable, PROVIDER] + args,
            input=stdin,
            capture_output=True,
            text=True,
            env=env,
        )
        return result

    def test_list_flattens_an_rrset(self):
        self.server.zone = [
            {"name": "www", "type": "A", "ttl": 300, "records": [{"content": "198.51.100.10"}]},
        ]
        result = self.run_provider(["list", "example.com"])
        self.assertEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertEqual(
            out,
            {"records": [{"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 300}]},
        )

    def test_list_leaves_out_a_type_that_cannot_round_trip(self):
        self.server.zone = [
            {"name": "@", "type": "MX", "ttl": 300, "records": [{"content": "10 example.com."}]},
            {"name": "www", "type": "A", "ttl": 300, "records": [{"content": "198.51.100.10"}]},
        ]
        result = self.run_provider(["list", "example.com"])
        out = json.loads(result.stdout)
        self.assertEqual(len(out["records"]), 1)
        self.assertEqual(out["records"][0]["type"], "A")

    def test_upsert_creates_by_appending_to_nothing(self):
        self.server.zone = []
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})
        puts = [r for r in self.server.requests if r[0] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertFalse(puts[0][2]["overwrite"])

    def test_upsert_does_nothing_when_the_value_is_already_right(self):
        self.server.zone = [
            {"name": "www", "type": "A", "ttl": 300, "records": [{"content": "198.51.100.10"}]},
        ]
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {})
        writes = [r for r in self.server.requests if r[0] in ("PUT", "DELETE")]
        self.assertEqual(writes, [])

    def test_upsert_replaces_rather_than_appends(self):
        self.server.zone = [
            {"name": "www", "type": "A", "ttl": 300, "records": [{"content": "198.51.100.10"}]},
        ]
        record = {"name": "www", "type": "A", "value": "198.51.100.20", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        # DELETE then PUT with overwrite: false. The one-call path needs
        # overwrite: true, and nothing Hostinger documents says the names
        # absent from that payload survive it.
        writes = [r for r in self.server.requests if r[0] in ("DELETE", "PUT")]
        self.assertEqual([w[0] for w in writes], ["DELETE", "PUT"])
        self.assertFalse(writes[1][2]["overwrite"])
        contents = writes[1][2]["zone"][0]["records"]
        self.assertEqual(len(contents), 1)
        self.assertEqual(contents[0]["content"], "198.51.100.20")

    def test_upsert_always_sends_overwrite_explicitly(self):
        # overwrite defaults to true on Hostinger's API; a request that omits
        # it is the destructive choice, so every PUT body carries the field.
        self.server.zone = [
            {"name": "www", "type": "A", "ttl": 300, "records": [{"content": "198.51.100.10"}]},
        ]
        record = {"name": "www", "type": "A", "value": "198.51.100.20", "ttl": 300}
        self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        puts = [r for r in self.server.requests if r[0] == "PUT"]
        for _, _, body in puts:
            self.assertIn("overwrite", body)

    def test_delete_takes_the_whole_set_when_it_holds_only_that_value(self):
        self.server.zone = [
            {"name": "www", "type": "A", "ttl": 300, "records": [{"content": "198.51.100.10"}]},
        ]
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 0}
        result = self.run_provider(["delete", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        deletes = [r for r in self.server.requests if r[0] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        puts = [r for r in self.server.requests if r[0] == "PUT"]
        self.assertEqual(puts, [])

    def test_delete_keeps_the_other_values_of_the_same_name(self):
        self.server.zone = [
            {
                "name": "www",
                "type": "A",
                "ttl": 300,
                "records": [{"content": "198.51.100.10"}, {"content": "198.51.100.20"}],
            },
        ]
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 0}
        result = self.run_provider(["delete", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        deletes = [r for r in self.server.requests if r[0] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        puts = [r for r in self.server.requests if r[0] == "PUT"]
        self.assertEqual(len(puts), 1)
        kept = puts[0][2]["zone"][0]["records"]
        self.assertEqual([r["content"] for r in kept], ["198.51.100.20"])

    def test_delete_with_no_value_takes_the_whole_set(self):
        self.server.zone = [
            {
                "name": "www",
                "type": "A",
                "ttl": 300,
                "records": [{"content": "198.51.100.10"}, {"content": "198.51.100.20"}],
            },
        ]
        record = {"name": "www", "type": "A", "value": "", "ttl": 0}
        result = self.run_provider(["delete", "example.com"], stdin=json.dumps(record))
        self.assertEqual(result.returncode, 0)
        deletes = [r for r in self.server.requests if r[0] == "DELETE"]
        self.assertEqual(len(deletes), 1)
        puts = [r for r in self.server.requests if r[0] == "PUT"]
        self.assertEqual(puts, [])

    def test_a_404_is_reported_as_zone_not_found(self):
        self.server.not_found = True
        result = self.run_provider(["list", "example.com"])
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertEqual(out["error"]["kind"], "zone_not_found")

    def test_a_401_is_reported_as_unauthenticated(self):
        self.server.zone = None
        result = self.run_provider(["list", "example.com"])
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertEqual(out["error"]["kind"], "unauthenticated")

    def test_a_429_is_reported_as_rate_limited_and_not_retried(self):
        self.server.zone = []
        self.server.rate_limited = True
        record = {"name": "www", "type": "A", "value": "198.51.100.10", "ttl": 300}
        result = self.run_provider(["upsert", "example.com"], stdin=json.dumps(record))
        self.assertNotEqual(result.returncode, 0)
        out = json.loads(result.stdout)
        self.assertEqual(out["error"]["kind"], "rate_limited")
        puts = [r for r in self.server.requests if r[0] == "PUT"]
        self.assertEqual(len(puts), 1)

    def test_zones_reports_what_the_token_can_see(self):
        self.server.portfolio = [{"domain": "example.com"}, {"domain": "example.net"}]
        result = self.run_provider(["zones"])
        self.assertEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout), {"zones": ["example.com", "example.net"]})

    def test_zones_takes_no_zone(self):
        # `zones` is how the CLI finds out which registrar holds a name, so
        # asking it for a zone first would be circular.
        self.server.portfolio = []
        self.assertEqual(self.run_provider(["zones"]).returncode, 0)

    def test_help_lists_every_command_the_manifest_declares(self):
        # `devmachine packages help` asks the package itself. A manifest that
        # declares a command the entrypoint refuses is a lie nothing catches.
        result = self.run_provider(["help"])
        self.assertEqual(result.returncode, 0)
        names = [c["name"] for c in json.loads(result.stdout)["commands"]]
        self.assertEqual(sorted(names), ["delete", "help", "list", "upsert", "zones"])

    def test_a_command_that_needs_a_zone_says_so(self):
        result = self.run_provider(["list"])
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(json.loads(result.stdout)["error"]["kind"], "invalid_record")

if __name__ == "__main__":
    unittest.main()
