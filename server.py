"""novel-gloss: type a French word on your phone, get a gloss, card goes into Anki.

Runs on the Mac next to Anki. Serves the phone page, asks Claude for the gloss,
and adds a note through AnkiConnect (localhost:8765). If Anki is closed, notes
wait in queue.json and are added the next time Anki is reachable.
"""

import json
import os
import re
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent


def load_env():
    env = ROOT / ".env"
    if env.exists():
        for line in env.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


load_env()

PORT = int(os.environ.get("PORT", "8787"))
DECK = os.environ.get("ANKI_DECK", "French::Novel")
MODEL_NAME = "Novel Gloss FR"
ANKI_URL = os.environ.get("ANKI_URL", "http://127.0.0.1:8765")
CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
EFFORT = os.environ.get("CLAUDE_EFFORT", "low")
QUEUE_FILE = ROOT / "queue.json"

_client = None
queue_lock = threading.Lock()
gloss_cache: dict[tuple, dict] = {}

# ---------------------------------------------------------------- Claude

SYSTEM = """You gloss French words for an English-speaking reader working through a French novel.
The word is typed exactly as it appeared on the page, so it may be inflected (passé simple, \
subjunctive, plural, feminine, elided like "qu'il"), literary, archaic, regional or slang, and \
may contain typos or missing accents; infer the intended word. If a sentence from the book is \
given, pick the sense that fits that sentence.

Field rules:
- lemma: dictionary form (infinitive for verbs, masculine singular for adjectives, singular for \
nouns). For a fixed expression, the expression.
- pos: one of noun, verb, adjective, adverb, preposition, conjunction, pronoun, expression, other.
- gender: "m", "f", or "" (nouns only).
- ipa: IPA of the lemma, no slashes.
- gloss: the English meaning in this context, at most ~6 words, the way a margin note would put it.
- other_senses: other common meanings, short, semicolon-separated; "" if none worth knowing.
- form: if the typed word differs from the lemma, name the form briefly in English \
(e.g. "passé simple, 3rd sg." or "fem. pl."); otherwise "".
- register: "literary", "archaic", "familiar", "slang", "vulgar", "formal", "regional", or "".
- example_fr: a short natural French sentence using the lemma in the same sense (not the \
reader's sentence).
- example_en: its translation.
- note: one short line of something genuinely useful (false friend, collocation, etymology hook, \
confusable word); "" if nothing worth saying."""

# lemma and gloss come first so they can be shown while the rest is still streaming
KEYS = [
    "lemma", "gloss", "pos", "gender", "form", "register", "ipa",
    "other_senses", "example_fr", "example_en", "note",
]
SCHEMA = {
    "type": "object",
    "properties": {k: {"type": "string"} for k in KEYS},
    "required": KEYS,
    "additionalProperties": False,
}

_JSON_STR = r'"((?:[^"\\]|\\.)*)"'
EARLY_RE = re.compile(r'"lemma"\s*:\s*' + _JSON_STR + r'\s*,\s*"gloss"\s*:\s*' + _JSON_STR)


def gloss_word(word: str, context: str, on_early=None) -> dict:
    """Glosses a word. on_early(lemma, gloss) fires as soon as those two fields have streamed in."""
    key = (word.lower(), context)
    if key in gloss_cache:
        return gloss_cache[key]
    prompt = f"Word: {word}"
    if context:
        prompt += f"\nSentence from the book: {context}"
    global _client
    if _client is None:
        _client = anthropic.Anthropic()
    buf, sent_early = "", False
    with _client.beta.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=4000,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
        output_config={
            "effort": EFFORT,
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    ) as stream:
        for text in stream.text_stream:
            buf += text
            if on_early and not sent_early:
                m = EARLY_RE.search(buf)
                if m:
                    sent_early = True
                    on_early(json.loads(f'"{m[1]}"'), json.loads(f'"{m[2]}"'))
        resp = stream.get_final_message()
    if resp.stop_reason == "refusal":
        raise RuntimeError("Claude declined to gloss this word.")
    # after a fallback the final text is the fallback model's, so read it from the final message
    blocks = list(resp.content)
    last_fb = max((i for i, b in enumerate(blocks) if b.type == "fallback"), default=-1)
    text = "".join(b.text for b in blocks[last_fb + 1:] if b.type == "text")
    data = json.loads(text)
    gloss_cache[key] = data
    return data


# ---------------------------------------------------------------- Anki

CARD_CSS = """
.card { font-family: -apple-system, "Helvetica Neue", sans-serif; font-size: 22px;
  text-align: center; color: #1d1d1f; background: #fff; padding: 12px; }
.night_mode .card, .nightMode.card { color: #eee; background: #1e1e1e; }
.lemma { font-size: 38px; font-weight: 600; }
.meta { color: #888; font-size: 16px; margin-top: 4px; }
.ctx { font-size: 18px; font-style: italic; margin-top: 18px; color: #555; }
.night_mode .ctx, .nightMode .ctx { color: #aaa; }
.gloss { font-size: 28px; margin: 10px 0; }
.small { font-size: 16px; text-align: left; max-width: 520px; margin: 8px auto; }
.lbl { color: #888; }
b.hl { color: #0a7cff; }
"""

FRONT = """<div class="lemma">{{Lemma}}</div>
{{#Context}}<div class="ctx">{{Context}}</div>{{/Context}}"""

BACK = """{{FrontSide}}<hr id="answer">
<div class="gloss">{{Gloss}}</div>
<div class="meta">{{POS}}{{#Gender}} · {{Gender}}{{/Gender}}{{#IPA}} · /{{IPA}}/{{/IPA}}{{#Register}} · {{Register}}{{/Register}}</div>
{{#Form}}<div class="small"><span class="lbl">On the page:</span> {{Word}} — {{Form}}</div>{{/Form}}
{{#OtherSenses}}<div class="small"><span class="lbl">Also:</span> {{OtherSenses}}</div>{{/OtherSenses}}
<div class="small">{{ExampleFr}}<br><span class="lbl">{{ExampleEn}}</span></div>
{{#Note}}<div class="small"><span class="lbl">Note:</span> {{Note}}</div>{{/Note}}
{{#Book}}<div class="meta">{{Book}}</div>{{/Book}}"""

FIELDS = [
    "Lemma", "Gloss", "POS", "Gender", "IPA", "Word", "Form", "Register",
    "OtherSenses", "ExampleFr", "ExampleEn", "Note", "Context", "Book",
]


def anki(action: str, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    with urllib.request.urlopen(ANKI_URL, body, timeout=3) as r:
        out = json.load(r)
    if out.get("error"):
        raise RuntimeError(out["error"])
    return out["result"]


def anki_up() -> bool:
    try:
        anki("version")
        return True
    except Exception:
        return False


_setup_done = False


def ensure_setup():
    global _setup_done
    if _setup_done:
        return
    if MODEL_NAME not in anki("modelNames"):
        anki(
            "createModel",
            modelName=MODEL_NAME,
            inOrderFields=FIELDS,
            css=CARD_CSS,
            cardTemplates=[{"Name": "Recognition", "Front": FRONT, "Back": BACK}],
        )
    anki("createDeck", deck=DECK)
    _setup_done = True


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def highlight(context: str, word: str) -> str:
    ctx = esc(context)
    if not word:
        return ctx
    i = ctx.lower().find(word.lower())
    if i < 0:
        return ctx
    return ctx[:i] + '<b class="hl">' + ctx[i:i + len(word)] + "</b>" + ctx[i + len(word):]


def build_note(item: dict) -> dict:
    g, word = item["gloss"], item["word"]
    fields = {
        "Lemma": esc(g["lemma"]),
        "Gloss": esc(g["gloss"]),
        "POS": esc(g["pos"]),
        "Gender": esc(g["gender"]),
        "IPA": esc(g["ipa"]),
        "Word": esc(word) if word.lower() != g["lemma"].lower() else "",
        "Form": esc(g["form"]),
        "Register": esc(g["register"]),
        "OtherSenses": esc(g["other_senses"]),
        "ExampleFr": esc(g["example_fr"]),
        "ExampleEn": esc(g["example_en"]),
        "Note": esc(g["note"]),
        "Context": highlight(item.get("context", ""), word),
        "Book": esc(item.get("book", "")),
    }
    tags = ["novel-gloss"]
    if item.get("book"):
        tags.append("book::" + "_".join(item["book"].split()))
    return {
        "deckName": DECK,
        "modelName": MODEL_NAME,
        "fields": fields,
        "tags": tags,
        "options": {"allowDuplicate": False, "duplicateScope": "collection"},
    }


def existing_note(lemma: str):
    """A note with this lemma in this note type or the user's FrenchAuto type."""
    lemma = lemma.replace('"', '').replace("*", "\\*").replace("_", "\\_")
    q = f'"Lemma:{lemma}" (note:"{MODEL_NAME}" OR note:FrenchAuto)'
    ids = anki("findNotes", query=q)
    return ids[0] if ids else None


def add_to_anki(item: dict) -> dict:
    """Returns {"status": "added"|"duplicate", "noteId": int}. Raises if Anki is down."""
    ensure_setup()
    dup = existing_note(item["gloss"]["lemma"])
    if dup:
        return {"status": "duplicate", "noteId": dup}
    note_id = anki("addNote", note=build_note(item))
    return {"status": "added", "noteId": note_id}


# ---------------------------------------------------------------- queue

def read_queue() -> list:
    try:
        return json.loads(QUEUE_FILE.read_text())
    except Exception:
        return []


def write_queue(items: list):
    QUEUE_FILE.write_text(json.dumps(items, ensure_ascii=False, indent=1))


def enqueue(item: dict):
    with queue_lock:
        q = read_queue()
        q.append(item)
        write_queue(q)


def flush_queue() -> int:
    with queue_lock:
        q = read_queue()
        if not q or not anki_up():
            return 0
        left, done = [], 0
        for item in q:
            try:
                add_to_anki(item)
                done += 1
            except Exception:
                left.append(item)
        write_queue(left)
        return done


def flusher():
    while True:
        try:
            n = flush_queue()
            if n:
                print(f"added {n} queued note(s) to Anki", flush=True)
        except Exception as e:
            print("queue flush error:", e, flush=True)
        time.sleep(30)


# ---------------------------------------------------------------- HTTP

class Handler(BaseHTTPRequestHandler):
    def log_message(self, fmt, *args):
        pass

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(n) or b"{}")

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            body = (ROOT / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/status":
            self.send_json({"anki": anki_up(), "queued": len(read_queue()), "deck": DECK})
        else:
            self.send_error(404)

    def lookup(self, word, context, book, add, on_early=None) -> dict:
        t0 = time.time()
        try:
            g = gloss_word(word, context, on_early)
        except Exception as e:
            print("gloss error:", repr(e), flush=True)
            raise
        ms = int((time.time() - t0) * 1000)
        item = {"word": word, "context": context, "book": book, "gloss": g}
        if add:
            try:
                anki_res = add_to_anki(item)
            except Exception as e:
                print("anki unavailable, queued:", repr(e), flush=True)
                enqueue(item)
                anki_res = {"status": "queued"}
        else:
            anki_res = {"status": "skipped"}
        print(f"{word} -> {g['lemma']}: {g['gloss']} [{ms} ms, {anki_res['status']}]", flush=True)
        return {"gloss": g, "anki": anki_res, "ms": ms}

    def do_POST(self):
        try:
            data = self.read_json()
        except Exception:
            return self.send_json({"error": "bad request"}, 400)

        if self.path in ("/api/gloss", "/api/lookup"):
            word = (data.get("word") or "").strip()
            context = (data.get("context") or "").strip()
            book = (data.get("book") or "").strip()
            add = data.get("add", True)
            if not word:
                return self.send_json({"error": "no word"}, 400)
            if self.path == "/api/gloss":  # plain JSON
                try:
                    return self.send_json(self.lookup(word, context, book, add))
                except Exception as e:
                    return self.send_json({"error": f"Gloss failed: {e}"}, 502)

            # /api/lookup: newline-delimited JSON, an "early" line with lemma + gloss, then "done"
            self.send_response(200)
            self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            def line(obj):
                self.wfile.write(json.dumps(obj, ensure_ascii=False).encode() + b"\n")
                self.wfile.flush()

            try:
                out = self.lookup(word, context, book, add,
                                  on_early=lambda l, g: line({"type": "early", "lemma": l, "gloss": g}))
                line({"type": "done", **out})
            except Exception as e:
                line({"type": "error", "error": f"Gloss failed: {e}"})
            return

        if self.path == "/api/undo":
            try:
                anki("deleteNotes", notes=[int(data["noteId"])])
                return self.send_json({"ok": True})
            except Exception as e:
                return self.send_json({"error": str(e)}, 502)

        self.send_error(404)


def lan_address() -> str:
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "localhost"


if __name__ == "__main__":
    threading.Thread(target=flusher, daemon=True).start()
    print(f"novel-gloss on http://{lan_address()}:{PORT}  (deck: {DECK}, model: {CLAUDE_MODEL})", flush=True)
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
