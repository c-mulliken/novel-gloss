# novel-gloss

Type a word from the novel you're reading on your phone → instant gloss → card lands in Anki.
French by default; also Spanish, Italian, Portuguese, German, Dutch, Swedish, Danish, Norwegian,
Polish, Czech, Russian and Greek. Each language gets its own deck.

## Setup (once)

1. Anki open on your computer, with the [AnkiConnect](https://ankiweb.net/shared/info/2055492159)
   add-on installed (Tools → Add-ons → Get Add-ons, code `2055492159`).
2. `cp .env.example .env` and put your Anthropic API key in it.
3. `./run.sh` — prints the address, e.g. `http://192.168.1.20:8787`.
4. On your phone (same Wi-Fi), open that address (or `http://<computer-name>.local:8787`),
   then Share → **Add to Home Screen**.

## Use

- Pick the language under the input (remembered), type the word exactly as printed
  (`bouleversa`, `fussent`, `dándoselo`, `aufgestanden`…), hit Go.
  The short gloss shows within a second or two; the full card follows.
- Optional: tap **+ sentence / book** to paste the sentence (picks the right sense, shown on the card
  with the word highlighted) and set the book title (remembered; becomes a `book::Title` tag).
- Cards go to `<Language>::Novel` (e.g. `French::Novel`, `German::Novel`), note type `Novel Gloss`,
  tagged `lang::fr` etc. Front: lemma + your sentence. Back: gloss, POS/gender/IPA, the form you saw,
  other senses, example, note.
- A lemma already in that language's deck isn't added twice. To also check note types of your own,
  set `ANKI_DUP_NOTE_TYPES_<CODE>` in `.env`.
- If Anki is closed, cards queue in `queue.json` and are added automatically once Anki is open.
- **Undo** on the result removes the card it just added.

## Config (`.env`)

See [`.env.example`](.env.example) for everything. The main ones:

| var | default | |
|---|---|---|
| `DEFAULT_LANGUAGE` | `fr` | language picked when the page first opens |
| `ANKI_DECK` | `{language}::Novel` | deck pattern; `{language}` = English name, `{code}` = `fr`, `de`… |
| `ANKI_DECK_<CODE>` | | deck for one language, e.g. `ANKI_DECK_DE=Deutsch::Vokabeln` |
| `ANKI_NOTE_TYPE` | `Novel Gloss` | note type for the cards (created if missing) |
| `ANKI_DUP_NOTE_TYPES_<CODE>` | | your own note types to check for duplicates |
| `ANKI_URL` / `ANKI_API_KEY` | `http://127.0.0.1:8765` / none | AnkiConnect address and key |
| `CLAUDE_MODEL` | `claude-opus-5-5` | |

Away from home Wi-Fi: install Tailscale on the computer and phone and use the computer's Tailscale name.
There's no login, so only run it on networks you trust.
