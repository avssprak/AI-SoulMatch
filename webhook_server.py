"""Standalone HTTP sidecar for payment-gateway webhooks (V3-3).

Streamlit serves a websocket app and cannot receive arbitrary HTTP POST
routes, so this tiny stdlib server runs ALONGSIDE the Streamlit app (see
run_local.ps1 and the V3-4 Docker Compose) on WEBHOOK_SERVER_PORT (default
8502), shares the same database via soulmatch.db, and does nothing else —
no new dependency (FastAPI/uvicorn) needed for two routes.

Run with:  .venv/Scripts/python.exe webhook_server.py

[HUMAN] step: point each gateway's webhook-endpoint config at
http://<your-domain>/webhooks/razorpay and /webhooks/stripe (the V3-4 Caddy
config proxies /webhooks/* to this port) and paste the webhook signing
secret each dashboard gives you into RAZORPAY_WEBHOOK_SECRET /
STRIPE_WEBHOOK_SECRET in .env.
"""

from __future__ import annotations

import hashlib
import json
import logging
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from soulmatch import config, payments
from soulmatch.db import get_session, init_db
from soulmatch.errors import init_error_reporting

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("webhook_server")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt: str, *args) -> None:  # quiet stdlib default; route through logging
        log.info("%s - %s", self.address_string(), fmt % args)

    def _respond(self, code: int, body: str = "") -> None:
        self.send_response(code)
        self.send_header("Content-Type", "text/plain")
        self.end_headers()
        if body:
            self.wfile.write(body.encode())

    def do_GET(self) -> None:
        self._respond(200, "ok") if self.path == "/" else self._respond(404)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(length) if length else b""
        if self.path == "/webhooks/razorpay":
            self._handle_razorpay(raw_body)
        elif self.path == "/webhooks/stripe":
            self._handle_stripe(raw_body)
        else:
            self._respond(404)

    def _handle_razorpay(self, raw_body: bytes) -> None:
        signature = self.headers.get("X-Razorpay-Signature", "")
        if not payments.verify_razorpay_signature(raw_body, signature, config.RAZORPAY_WEBHOOK_SECRET):
            log.warning("Razorpay webhook: signature verification failed")
            self._respond(400, "invalid signature")
            return
        try:
            event = json.loads(raw_body)
        except ValueError:
            self._respond(400, "invalid json")
            return
        # Razorpay events don't reliably carry a unique top-level id; the raw
        # body hash is a correct idempotency key since identical retried
        # deliveries have identical bodies.
        event_id = event.get("id") or hashlib.sha256(raw_body).hexdigest()
        with get_session() as session:
            if payments.is_new_event(session, "razorpay", str(event_id)):
                payments.apply_razorpay_event(session, event)
        self._respond(200, "ok")

    def _handle_stripe(self, raw_body: bytes) -> None:
        sig_header = self.headers.get("Stripe-Signature", "")
        if not payments.verify_stripe_signature(raw_body, sig_header, config.STRIPE_WEBHOOK_SECRET):
            log.warning("Stripe webhook: signature verification failed")
            self._respond(400, "invalid signature")
            return
        try:
            event = json.loads(raw_body)
        except ValueError:
            self._respond(400, "invalid json")
            return
        event_id = event.get("id")
        if not event_id:
            self._respond(400, "missing event id")
            return
        with get_session() as session:
            if payments.is_new_event(session, "stripe", event_id):
                payments.apply_stripe_event(session, event)
        self._respond(200, "ok")


def main() -> None:
    init_error_reporting()
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", config.WEBHOOK_SERVER_PORT), Handler)
    log.info(
        "Webhook sidecar listening on :%d (razorpay: /webhooks/razorpay, stripe: /webhooks/stripe)",
        config.WEBHOOK_SERVER_PORT,
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
