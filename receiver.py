"""Minimal webhook receiver for the e2e test: logs every POST body to receiver.log."""
import json, sys, time
from http.server import BaseHTTPRequestHandler, HTTPServer

LOG = sys.argv[1] if len(sys.argv) > 1 else "receiver.log"

class H(BaseHTTPRequestHandler):
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(n).decode("utf-8", "replace")
        with open(LOG, "a") as f:
            f.write(json.dumps({"ts": time.time(), "path": self.path, "headers": dict(self.headers), "body": body}) + "\n")
        self.send_response(200); self.end_headers(); self.wfile.write(b"ok")
    def log_message(self, *a):  # quiet
        pass

HTTPServer(("0.0.0.0", 8099), H).serve_forever()
