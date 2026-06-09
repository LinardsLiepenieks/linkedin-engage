#!/usr/bin/env python3
"""
serve_review.py — Local web UI to review, edit, and approve drafted comments.

Reads data/review.json (posts + Claude's draft comments + scores) and serves a page at
http://localhost:8765 where you can:
  * read each qualifying post,
  * edit the drafted comment,
  * toggle include / like / follow per post,
  * rate the DRAFT 👍 / 👎 (feedback on the draft quality, independent of edits),
  * click "Save approvals" -> writes data/approved.json.

After you save, the page tells you it's safe to close, and you return to the skill to run
the apply step. Press Ctrl+C here to stop the server.

Usage:
    python scripts/serve_review.py
"""

import json
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
REVIEW_FILE = DATA_DIR / "review.json"
APPROVED_FILE = DATA_DIR / "approved.json"
HOST, PORT = "127.0.0.1", 8765

PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>LinkedIn engage — review</title>
<style>
  :root { --bg:#0d1117; --card:#161b22; --line:#30363d; --fg:#e6edf3; --muted:#8b949e;
          --accent:#2f81f7; --good:#3fb950; }
  * { box-sizing:border-box; }
  body { margin:0; font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
         background:var(--bg); color:var(--fg); }
  header { position:sticky; top:0; background:var(--bg); border-bottom:1px solid var(--line);
           padding:16px 24px; display:flex; align-items:center; gap:16px; z-index:10; }
  header h1 { font-size:18px; margin:0; flex:1; }
  .count { color:var(--muted); font-size:14px; }
  button { font:inherit; cursor:pointer; border-radius:8px; border:1px solid var(--line);
           background:var(--card); color:var(--fg); padding:8px 14px; }
  button.primary { background:var(--accent); border-color:var(--accent); color:#fff; font-weight:600; }
  main { max-width:820px; margin:0 auto; padding:24px; }
  .card { background:var(--card); border:1px solid var(--line); border-radius:12px;
          padding:18px; margin-bottom:18px; }
  .card.excluded { opacity:.5; }
  .row { display:flex; gap:12px; align-items:flex-start; }
  .score { font-weight:700; font-size:13px; padding:3px 8px; border-radius:999px;
           background:rgba(63,185,80,.15); color:var(--good); white-space:nowrap; }
  .author { font-weight:600; }
  .headline { color:var(--muted); font-size:13px; }
  .post { white-space:pre-wrap; margin:12px 0; padding:12px; background:#0d1117;
          border:1px solid var(--line); border-radius:8px; max-height:220px; overflow:auto;
          font-size:14px; }
  .meta { color:var(--muted); font-size:12px; margin-bottom:8px; }
  .reason { color:var(--muted); font-size:13px; font-style:italic; margin-bottom:10px; }
  label.cmt { font-size:12px; color:var(--muted); display:block; margin-bottom:4px; }
  textarea { width:100%; min-height:72px; resize:vertical; background:#0d1117; color:var(--fg);
             border:1px solid var(--line); border-radius:8px; padding:10px; font:inherit; }
  .toggles { display:flex; gap:18px; margin-top:10px; font-size:14px; align-items:center; }
  .toggles label { display:flex; gap:6px; align-items:center; cursor:pointer; }
  .rate { display:flex; gap:6px; margin-left:auto; }
  .ratebtn { padding:4px 10px; font-size:15px; line-height:1; opacity:.55; }
  .ratebtn.active { opacity:1; }
  .ratebtn.active.up { border-color:var(--good); background:rgba(63,185,80,.15); }
  .ratebtn.active.down { border-color:#f85149; background:rgba(248,81,73,.15); }
  a.permalink { color:var(--accent); text-decoration:none; font-size:12px; }
  #status { color:var(--good); font-weight:600; }
  .empty { text-align:center; color:var(--muted); padding:60px; }
</style>
</head>
<body>
<header>
  <h1>Review drafts</h1>
  <span class="count" id="counter"></span>
  <span id="status"></span>
  <button class="primary" onclick="save()">Save approvals</button>
</header>
<main id="list"></main>

<script>
let DATA = [];

async function load() {
  const r = await fetch('/data');
  DATA = await r.json();
  render();
}

function render() {
  const list = document.getElementById('list');
  if (!DATA.length) {
    list.innerHTML = '<div class="empty">No qualifying posts in review.json.</div>';
    updateCounter();
    return;
  }
  list.innerHTML = '';
  DATA.forEach((d, i) => {
    const card = document.createElement('div');
    card.className = 'card' + (d.include ? '' : ' excluded');
    card.id = 'card-' + i;
    card.innerHTML = `
      <div class="row">
        <span class="score">${d.score}/10</span>
        <div style="flex:1">
          <div class="author">${esc(d.author || 'Unknown')}</div>
          <div class="headline">${esc(d.headline || '')}</div>
        </div>
        <a class="permalink" href="${d.permalink}" target="_blank">open ↗</a>
      </div>
      <div class="meta">👍 ${d.reactions ?? 0} · 💬 ${d.comments ?? 0}</div>
      ${d.reason ? `<div class="reason">${esc(d.reason)}</div>` : ''}
      <div class="post">${esc(d.text || '(no text extracted)')}</div>
      <label class="cmt">Your comment</label>
      <textarea oninput="DATA[${i}].comment=this.value">${esc(d.comment || '')}</textarea>
      <div class="toggles">
        <label><input type="checkbox" ${d.include ? 'checked':''}
            onchange="DATA[${i}].include=this.checked; toggleCard(${i})"> include</label>
        <label><input type="checkbox" ${d.like ? 'checked':''}
            onchange="DATA[${i}].like=this.checked"> like</label>
        <label><input type="checkbox" ${d.follow ? 'checked':''}
            onchange="DATA[${i}].follow=this.checked"> follow author</label>
        <span class="rate" title="Rate this draft (feeds learning at end of run)">
          <button type="button" id="up-${i}" class="ratebtn ${d.rating==='up'?'active up':''}"
              onclick="ratePost(${i},'up')">👍</button>
          <button type="button" id="down-${i}" class="ratebtn ${d.rating==='down'?'active down':''}"
              onclick="ratePost(${i},'down')">👎</button>
        </span>
      </div>`;
    list.appendChild(card);
  });
  updateCounter();
}

function toggleCard(i){ document.getElementById('card-'+i).classList.toggle('excluded', !DATA[i].include); updateCounter(); }
function ratePost(i, val){
  DATA[i].rating = (DATA[i].rating === val) ? null : val;   // click again to clear
  document.getElementById('up-'+i).classList.toggle('active', DATA[i].rating==='up');
  document.getElementById('up-'+i).classList.toggle('up', DATA[i].rating==='up');
  document.getElementById('down-'+i).classList.toggle('active', DATA[i].rating==='down');
  document.getElementById('down-'+i).classList.toggle('down', DATA[i].rating==='down');
}
function updateCounter(){
  const n = DATA.filter(d=>d.include).length;
  document.getElementById('counter').textContent = n + ' of ' + DATA.length + ' selected';
}
function esc(s){ return (s??'').toString().replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c])); }

async function save(){
  const r = await fetch('/approve', {method:'POST', headers:{'Content-Type':'application/json'},
                                     body: JSON.stringify(DATA)});
  if (r.ok) {
    const n = DATA.filter(d=>d.include).length;
    document.getElementById('status').textContent =
      `Saved ${n} approved ✓ — safe to close this tab, then run the apply step.`;
  } else {
    document.getElementById('status').textContent = 'Save failed — check the terminal.';
  }
}
load();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quieter
        pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        if self.path == "/":
            self._send(200, PAGE)
        elif self.path == "/data":
            data = json.loads(REVIEW_FILE.read_text()) if REVIEW_FILE.exists() else []
            # ensure default toggles exist
            for d in data:
                d.setdefault("include", True)
                d.setdefault("like", False)
                d.setdefault("follow", False)
                d.setdefault("rating", None)  # "up" | "down" | None — draft-quality feedback
            self._send(200, json.dumps(data), "application/json")
        else:
            self._send(404, "not found")

    def do_POST(self):
        if self.path == "/approve":
            length = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(length) or b"[]")
            APPROVED_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
            n = sum(1 for d in payload if d.get("include"))
            print(f"  saved {n} approved item(s) -> {APPROVED_FILE}")
            self._send(200, json.dumps({"ok": True}), "application/json")
        else:
            self._send(404, "not found")


def main():
    if not REVIEW_FILE.exists():
        print(f"WARNING: {REVIEW_FILE} not found yet. The page will show 'no posts' until "
              f"Claude writes review.json.")
    url = f"http://{HOST}:{PORT}/"
    print(f"Review UI at {url}  (Ctrl+C to stop)")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    HTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
