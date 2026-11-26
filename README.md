# novel-gloss

Type a French word from your novel on your phone → instant gloss → card lands in Anki.

## Setup (once)

1. Anki open on the Mac, with the AnkiConnect add-on (code `2055492159`). Already installed here.
2. `cp .env.example .env` and put your Anthropic API key in it.
3. `./run.sh` — prints the address, e.g. `http://10.1.10.132:8787`.
4. On your phone (same Wi-Fi), open `http://MacBook-Air-587.local:8787`
   (or the IP it prints), then Share → **Add to Home Screen**.

## Use

- Type the word exactly as printed (`bouleversa`, `qu'eût`, `fussent`…), hit Go.
- Optional: tap **+ sentence / book** to paste the sentence (picks the right sense, shown on the card
  with the word highlighted) and set the book title (remembered; becomes a `book::Title` tag).
- Cards go to deck `French::Novel`, note type `Novel Gloss FR`. Front: lemma + your sentence.
  Back: gloss, POS/gender/IPA, the form you saw, other senses, example, note.
- If a lemma already exists (in this note type or your `FrenchAuto` cards), it isn't added twice.
- If Anki is closed, cards queue in `queue.json` and are added automatically once Anki is open.
- **Undo** on the result removes the card it just added.

## Config (`.env`)

| var | default | |
|---|---|---|
| `ANKI_DECK` | `French::Novel` | target deck |
| `CLAUDE_MODEL` | `claude-opus-5-5` | `claude-haiku-5-5` is faster and far cheaper |
| `CLAUDE_EFFORT` | `low` | |
| `PORT` | `8787` | |

Away from home Wi-Fi: install Tailscale on the Mac and phone and use the Mac's Tailscale name instead.
There's no login, so only run it on networks you trust.
