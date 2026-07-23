#!/usr/bin/env python3
"""Private localhost desk for blinded weekly field-validation review."""

from __future__ import annotations

import argparse
import hashlib
import hmac
import html
import json
import re
import secrets
import sqlite3
import sys
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlencode, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from commons_lab.schema import migrate
from commons_lab.safe_paths import read_bytes_no_symlinks
from commons_lab.validation import (
    PROTOCOL_VERSION,
    record_validation_review,
    validation_report,
    wav_span_bytes,
)

DEFAULT_DB = ROOT / "archive.db"
ITEM_ID_PATTERN = re.compile(r"^vit_[0-9a-f]{24}$")
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
MAX_FORM_BYTES = 64 * 1024


def connect(path: Path | str) -> sqlite3.Connection:
    conn = sqlite3.connect(Path(path), timeout=30)
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA busy_timeout=30000")
    return conn


def _checked_item_id(item_id: str) -> str:
    if not ITEM_ID_PATTERN.fullmatch(item_id):
        raise ValueError("invalid validation item ID")
    return item_id


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _page(title: str, body: str) -> str:
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title>
<style>
:root{{--ink:#e8efe9;--muted:#a9b9ae;--ground:#101713;--panel:#19231d;--edge:#34463a;--moss:#8fcf8d;--warn:#e9ca75}}
*{{box-sizing:border-box}} body{{margin:0;background:var(--ground);color:var(--ink);font:16px/1.5 system-ui,sans-serif}}
main{{max-width:900px;margin:0 auto;padding:28px 18px 70px}} a{{color:var(--moss)}}
.card{{background:var(--panel);border:1px solid var(--edge);border-radius:12px;padding:18px;margin:14px 0}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}}
label{{display:block;margin:10px 0}} fieldset{{border:1px solid var(--edge);border-radius:10px;margin:14px 0;padding:14px}}
legend{{font-weight:700}} input[type=text],textarea{{width:100%;background:#0e1511;color:var(--ink);border:1px solid var(--edge);border-radius:7px;padding:10px}}
button{{background:var(--moss);color:#102014;border:0;border-radius:8px;padding:11px 18px;font-weight:700;cursor:pointer}}
small,.muted{{color:var(--muted)}} audio{{width:100%;margin:8px 0}} table{{width:100%;border-collapse:collapse}}
th,td{{text-align:left;border-bottom:1px solid var(--edge);padding:8px}} code,pre{{white-space:pre-wrap;word-break:break-word;background:#0d140f;padding:2px 5px;border-radius:4px}}
.notice{{border-left:4px solid var(--warn);padding-left:12px}} .progress{{font-size:1.25rem;font-weight:700}}
</style></head><body><main>{body}</main></body></html>"""


def _packet_progress(conn: sqlite3.Connection, packet_id: str) -> tuple[int, int]:
    total, completed = conn.execute(
        """
        SELECT COUNT(*),SUM(CASE WHEN state='completed' THEN 1 ELSE 0 END)
        FROM commons_validation_items WHERE packet_id=?
        """,
        (packet_id,),
    ).fetchone()
    return int(completed or 0), int(total or 0)


def render_home_page(conn: sqlite3.Connection) -> str:
    packets = conn.execute(
        """
        SELECT packet_id,week_start,state,manifest_sha256 FROM commons_validation_packets
        WHERE protocol_version=?
        ORDER BY week_start DESC
        """,
        (PROTOCOL_VERSION,),
    ).fetchall()
    cards: list[str] = []
    for packet_id, week_start, state, manifest_sha256 in packets:
        completed, total = _packet_progress(conn, str(packet_id))
        next_item = conn.execute(
            """
            SELECT item_id FROM commons_validation_items
            WHERE packet_id=? AND state='pending' ORDER BY position LIMIT 1
            """,
            (packet_id,),
        ).fetchone()
        action = (
            f'<a href="/review?{urlencode({"item_id": next_item[0]})}">Continue blinded review</a>'
            if next_item is not None
            else "Packet review complete"
        )
        cards.append(
            f"""<section class="card"><h2>Week of {html.escape(str(week_start))}</h2>
<p class="progress">{completed} / {total} reviewed</p>
<p>State: <strong>{html.escape(str(state))}</strong></p><p>{action}</p>
<p><a href="/report?{urlencode({'packet_id': str(packet_id)})}">Scientific report</a></p>
<small>Manifest {html.escape(str(manifest_sha256))}</small></section>"""
        )
    if not cards:
        cards.append('<section class="card"><p>No weekly packet exists yet.</p></section>')
    body = """<h1>Pine Hollow Field Validation Desk</h1>
<p>Private, blinded review of exact archived acoustic spans.</p>
<p class="notice">This desk records human evidence. It does not retrain models, change thresholds, or publish media.</p>""" + "".join(cards)
    return _page("Field Validation Desk", body)


def render_review_page(
    conn: sqlite3.Connection, *, item_id: str, csrf_token: str
) -> str:
    item_id = _checked_item_id(item_id)
    row = conn.execute(
        """
        SELECT i.packet_id,i.position,i.state,i.start_sample,i.end_sample,
               i.sample_rate,p.target_count,p.week_start,e.started_at,p.protocol_version
        FROM commons_validation_items AS i
        JOIN commons_validation_packets AS p ON p.packet_id=i.packet_id
        JOIN commons_events AS e ON e.event_id=i.event_id
        WHERE i.item_id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError("validation item does not exist")
    if str(row[9]) != PROTOCOL_VERSION:
        raise ValueError("validation item belongs to an inactive validation protocol")
    packet_id = str(row[0])
    position = int(row[1])
    if str(row[2]) == "completed":
        return _page(
            "Review complete",
            f"""<h1>Review already complete</h1><p>This judgment is append-only.</p>
<p><a href="/reveal?{urlencode({'item_id': item_id})}">Reveal model context</a></p>
<p><a href="/">Return to packets</a></p>""",
        )
    completed, total = _packet_progress(conn, packet_id)
    duration = (int(row[4]) - int(row[3])) / int(row[5])
    body = f"""<h1>Blinded field validation</h1>
<p class="progress">Item {position} of {int(row[6])} · {completed} saved</p>
<section class="card"><h2>Exact five-second window</h2>
<audio controls preload="metadata" src="/audio/{item_id}?{urlencode({'scope': 'window', 'token': csrf_token})}"></audio>
<small>Scored span: {duration:.3f} seconds. Judge this span.</small></section>
<section class="card"><h2>Full 15-second context</h2>
<audio controls preload="none" src="/audio/{item_id}?{urlencode({'scope': 'full', 'token': csrf_token})}"></audio>
<small>Context only. The judgment remains attached to the exact span above.</small></section>
<form method="post" action="/review">
<input type="hidden" name="csrf_token" value="{html.escape(csrf_token, quote=True)}">
<input type="hidden" name="item_id" value="{html.escape(item_id, quote=True)}">
<fieldset><legend>Insect audible in the exact window?</legend>
<label><input required type="radio" name="insect_presence" value="present"> Yes</label>
<label><input type="radio" name="insect_presence" value="absent"> No</label>
<label><input type="radio" name="insect_presence" value="uncertain"> Unsure</label></fieldset>
<fieldset><legend>Chicken vocalization audible in the exact window?</legend>
<label><input required type="radio" name="chicken_presence" value="present"> Yes</label>
<label><input type="radio" name="chicken_presence" value="absent"> No</label>
<label><input type="radio" name="chicken_presence" value="uncertain"> Unsure</label></fieldset>
<fieldset><legend>Frog or toad vocalization audible in the exact window?</legend>
<label><input required type="radio" name="frog_presence" value="present"> Yes</label>
<label><input type="radio" name="frog_presence" value="absent"> No</label>
<label><input type="radio" name="frog_presence" value="uncertain"> Unsure</label></fieldset>
<fieldset><legend>Signal quality</legend>
{''.join(f'<label><input required type="radio" name="signal_quality" value="{value}"> {label}</label>' for value, label in [('clear','Clear'),('distant','Distant'),('overlapping','Overlapping'),('clipped','Clipped'),('noisy','Wind/rain/noise'),('inaudible','Inaudible')])}</fieldset>
<fieldset><legend>Confounders, if present</legend>
{''.join(f'<label><input type="checkbox" name="confounder" value="{value}"> {label}</label>' for value, label in [('bird_overlap','Bird overlap'),('wind','Wind'),('rain','Rain'),('mechanical','Mechanical'),('human_activity','Human activity'),('clipping','Clipping'),('unknown','Unknown')])}</fieldset>
<label>Reviewer authority<input required type="text" name="reviewer" value="human:field-reviewer" maxlength="120"></label>
<label>Notes<textarea name="notes" maxlength="4000" rows="4"></textarea></label>
<button type="submit">Save append-only judgment</button></form>
<p class="muted">Recorded {html.escape(str(row[8]))}. Sampling lane and model output remain hidden until this judgment is saved.</p>"""
    return _page("Blinded field validation", body)


def render_reveal_page(conn: sqlite3.Connection, *, item_id: str) -> str:
    item_id = _checked_item_id(item_id)
    row = conn.execute(
        """
        SELECT i.packet_id,i.position,i.lane,i.primary_class_name,
               i.sampling_metadata_json,r.insect_presence,r.chicken_presence,
               r.frog_presence,r.signal_quality,r.reviewed_at
        FROM commons_validation_items AS i
        LEFT JOIN commons_validation_reviews AS r ON r.item_id=i.item_id
        WHERE i.item_id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError("validation item does not exist")
    if row[5] is None:
        raise ValueError("validation item is not yet reviewed")
    metadata = json.loads(str(row[4]))
    context_rows = []
    for class_name, context in sorted(metadata["model_context"].items()):
        context_rows.append(
            "<tr>"
            f"<td>{html.escape(class_name)}</td>"
            f"<td>{html.escape(str(context['model_slug']))}</td>"
            f"<td>{float(context['score']):.8f}</td>"
            f"<td>{float(context['threshold']):.8f}</td>"
            f"<td>{'yes' if context['crosses_threshold'] else 'no'}</td>"
            "</tr>"
        )
    body = f"""<h1>Post-review model context</h1>
<section class="card"><p>Packet <code>{html.escape(str(row[0]))}</code> · item {int(row[1])}</p>
<p>Sampling selection: <strong>{html.escape(str(metadata['selection']))}</strong></p>
<p>Lane: <strong>{html.escape(str(row[2]))}</strong></p>
<p>Your judgment: insect <strong>{html.escape(str(row[5]))}</strong>; chicken <strong>{html.escape(str(row[6]))}</strong>; frog <strong>{html.escape(str(row[7]))}</strong>; quality <strong>{html.escape(str(row[8]))}</strong>.</p></section>
<table><thead><tr><th>Target</th><th>Model</th><th>Ranking score</th><th>Diagnostic threshold</th><th>Crossed</th></tr></thead>
<tbody>{''.join(context_rows)}</tbody></table>
<p class="notice">Scores are uncalibrated ranking scores, not probabilities.</p>
<p><a href="/">Return to packet</a> · <a href="/report?{urlencode({'packet_id': str(row[0])})}">View report</a></p>"""
    return _page("Post-review context", body)


def render_report_page(conn: sqlite3.Connection, *, packet_id: str | None) -> str:
    report = validation_report(conn, packet_id=packet_id)
    body = f"""<h1>Scientific validation report</h1>
<p>Scope: <strong>{html.escape(report['scope'])}</strong></p>
<pre>{html.escape(json.dumps(report, indent=2, sort_keys=True))}</pre>
<p><a href="/">Return to packets</a></p>"""
    return _page("Scientific validation report", body)


def verified_item_audio(
    conn: sqlite3.Connection, *, item_id: str, scope: str
) -> bytes:
    item_id = _checked_item_id(item_id)
    if scope not in {"window", "full"}:
        raise ValueError("audio scope must be window or full")
    row = conn.execute(
        """
        SELECT m.path,m.sha256,i.start_sample,i.end_sample,i.sample_rate,
               i.sampling_metadata_json,p.protocol_version
        FROM commons_validation_items AS i
        JOIN commons_media AS m ON m.media_id=i.media_id
        JOIN commons_validation_packets AS p ON p.packet_id=i.packet_id
        WHERE i.item_id=?
        """,
        (item_id,),
    ).fetchone()
    if row is None:
        raise ValueError("validation item does not exist")
    if str(row[6]) != PROTOCOL_VERSION:
        raise ValueError("validation item belongs to an inactive validation protocol")
    try:
        source_bytes = read_bytes_no_symlinks(str(row[0]))
    except (OSError, ValueError) as exc:
        raise ValueError("validation audio is unavailable or symlinked") from exc
    actual = hashlib.sha256(source_bytes).hexdigest()
    metadata = json.loads(str(row[5]))
    frozen = str(metadata.get("media_sha256", ""))
    if actual != str(row[1]) or actual != frozen:
        raise ValueError("validation audio hash does not match frozen evidence")
    if scope == "full":
        return source_bytes
    return wav_span_bytes(
        source_bytes,
        start_sample=int(row[2]),
        end_sample=int(row[3]),
        span_sample_rate=int(row[4]),
    )


class ValidationDeskServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        db_path: Path,
        csrf_token: str,
    ) -> None:
        self.db_path = db_path
        self.csrf_token = csrf_token
        self.review_started: dict[str, float] = {}
        super().__init__(address, ValidationDeskHandler)


class ValidationDeskHandler(BaseHTTPRequestHandler):
    @property
    def desk_server(self) -> ValidationDeskServer:
        return cast(ValidationDeskServer, self.server)

    def log_message(self, format: str, *args: Any) -> None:
        message = format % args
        message = re.sub(
            r"([?&]token=)[^&\s]+", r"\1[REDACTED]", message
        )
        sys.stderr.write("validation-desk: " + message + "\n")

    def _headers(self, status: int, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; media-src 'self'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _send(self, status: int, payload: bytes, content_type: str) -> None:
        self._headers(status, content_type, len(payload))
        self.wfile.write(payload)

    def _send_html(self, body: str, status: int = 200) -> None:
        self._send(status, body.encode("utf-8"), "text/html; charset=utf-8")

    def _connect(self) -> sqlite3.Connection:
        return connect(self.desk_server.db_path)

    def _loopback_host_header(self) -> bool:
        value = self.headers.get("Host", "").lower()
        return (
            value == "localhost"
            or value.startswith("localhost:")
            or value == "127.0.0.1"
            or value.startswith("127.0.0.1:")
            or value == "[::1]"
            or value.startswith("[::1]:")
        )

    def do_GET(self) -> None:
        if not self._loopback_host_header():
            self.send_error(421)
            return
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        try:
            if parsed.path == "/healthz":
                payload = json.dumps(
                    {"status": "ok", "bind": self.desk_server.server_address[0]}
                ).encode("utf-8")
                self._send(200, payload, "application/json")
                return
            if parsed.path == "/":
                conn = self._connect()
                try:
                    self._send_html(render_home_page(conn))
                finally:
                    conn.close()
                return
            if parsed.path == "/review":
                item_id = params.get("item_id", [None])[0]
                conn = self._connect()
                try:
                    if item_id is None:
                        row = conn.execute(
                            """
                            SELECT i.item_id FROM commons_validation_items AS i
                            JOIN commons_validation_packets AS p ON p.packet_id=i.packet_id
                            WHERE i.state='pending' AND p.protocol_version=?
                            ORDER BY p.week_start DESC,i.position LIMIT 1
                            """,
                            (PROTOCOL_VERSION,),
                        ).fetchone()
                        if row is None:
                            self._send_html(render_home_page(conn))
                            return
                        item_id = str(row[0])
                    self.desk_server.review_started[item_id] = time.monotonic()
                    self._send_html(
                        render_review_page(
                            conn, item_id=item_id, csrf_token=self.desk_server.csrf_token
                        )
                    )
                finally:
                    conn.close()
                return
            if parsed.path == "/reveal":
                item_id = params.get("item_id", [""])[0]
                conn = self._connect()
                try:
                    self._send_html(render_reveal_page(conn, item_id=item_id))
                finally:
                    conn.close()
                return
            if parsed.path == "/report":
                packet_id = params.get("packet_id", [None])[0]
                conn = self._connect()
                try:
                    self._send_html(render_report_page(conn, packet_id=packet_id))
                finally:
                    conn.close()
                return
            if parsed.path.startswith("/audio/"):
                token = params.get("token", [""])[0]
                if not hmac.compare_digest(token, self.desk_server.csrf_token):
                    self.send_error(403)
                    return
                item_id = parsed.path.removeprefix("/audio/")
                scope = params.get("scope", ["window"])[0]
                conn = self._connect()
                try:
                    payload = verified_item_audio(conn, item_id=item_id, scope=scope)
                finally:
                    conn.close()
                self._send(200, payload, "audio/wav")
                return
            self.send_error(404)
        except ValueError as exc:
            self._send_html(
                _page("Validation request rejected", f"<h1>Request rejected</h1><p>{html.escape(str(exc))}</p>"),
                400,
            )
        except Exception:
            self._send_html(
                _page("Validation desk error", "<h1>Validation desk error</h1><p>The request failed without changing review evidence.</p>"),
                500,
            )

    def do_POST(self) -> None:
        if not self._loopback_host_header():
            self.send_error(421)
            return
        parsed = urlparse(self.path)
        if parsed.path != "/review":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if length <= 0 or length > MAX_FORM_BYTES:
            self.send_error(413)
            return
        form = parse_qs(self.rfile.read(length).decode("utf-8"), keep_blank_values=True)
        token = form.get("csrf_token", [""])[0]
        if not hmac.compare_digest(token, self.desk_server.csrf_token):
            self.send_error(403)
            return
        item_id = form.get("item_id", [""])[0]
        started = self.desk_server.review_started.pop(item_id, None)
        review_seconds = None if started is None else max(0.0, time.monotonic() - started)
        conn = self._connect()
        try:
            result = record_validation_review(
                conn,
                item_id=item_id,
                reviewer=form.get("reviewer", [""])[0],
                insect_presence=form.get("insect_presence", [""])[0],
                chicken_presence=form.get("chicken_presence", [""])[0],
                frog_presence=form.get("frog_presence", [""])[0],
                signal_quality=form.get("signal_quality", [""])[0],
                confounders=form.get("confounder", []),
                notes=form.get("notes", [None])[0],
                review_seconds=review_seconds,
                reviewed_at=datetime.now(timezone.utc).isoformat(),
            )
        except ValueError as exc:
            conn.close()
            self._send_html(
                _page("Review rejected", f"<h1>Review rejected</h1><p>{html.escape(str(exc))}</p>"),
                400,
            )
            return
        except Exception:
            conn.close()
            self._send_html(
                _page("Review failed", "<h1>Review failed</h1><p>No partial review was retained.</p>"),
                500,
            )
            return
        conn.close()
        location = "/reveal?" + urlencode({"item_id": result.item_id})
        self.send_response(303)
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()


def create_server(
    *,
    db_path: Path | str,
    host: str = "127.0.0.1",
    port: int = 8765,
    csrf_token: str | None = None,
) -> ValidationDeskServer:
    if host not in LOOPBACK_HOSTS:
        raise ValueError("validation desk may bind only to loopback")
    path = Path(db_path).expanduser().resolve()
    conn = connect(path)
    migrate(conn)
    conn.close()
    return ValidationDeskServer((host, port), path, csrf_token or secrets.token_urlsafe(32))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, default=DEFAULT_DB)
    parser.add_argument("--host", choices=sorted(LOOPBACK_HOSTS), default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    server = create_server(db_path=args.db, host=args.host, port=args.port)
    print(f"Pine Hollow Field Validation Desk: http://{args.host}:{server.server_address[1]}")
    print("Loopback only. Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
