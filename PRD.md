# Prince Song Tagger — Lean PRD (Personal)

*Last updated: 2025‑08‑26*  
**Current Status: Phase 1 Complete — Basic metadata extraction working**

---

## Simple PRD (MVP Cut)

### Objective

Take a random MP3/FLAC and give it clean tags and light context so it’s pleasant to listen to and easy to find in a large Prince bootleg library.

### Scope

* **In**: MP3, FLAC; macOS; CLI; single & batch; Tag‑only (default) or Copy+Place; OpenAI LLM used on every file; PrinceVault SQLite + MusicBrainz + AcoustID.
* **Out**: complex UIs, manifests/undo, auto‑apply, moving/deleting originals, bulk library re‑org, scraping beyond MB/AcoustID.

### Dependencies

* Python 3.11+, `chromaprint` (AcoustID), `pyacoustid`, `mutagen`, `httpx`, `sqlite3`, `rapidfuzz`.
* OpenAI API key; AcoustID key; local PrinceVault **SQLite** file.

### Modes

* **Tag‑only (default):** write tags in place; no rename/move/copy.
* **Copy+Place (optional):** copy to destination and tag the copy; originals untouched.

### Minimal Tags Written

`ARTIST, TITLE, DATE, CITY, VENUE, SOURCE, ALBUM(optional), TRACKNUMBER(optional), MUSICBRAINZ_RECORDINGID, ACOUSTID, PV_CONCERT_ID(optional), COMMENT/NOTES`

### Folder & Filename Rules

Live in a user‑editable text file (e.g., `prefs/naming.md`) that is **passed to the LLM**. Change structure without changing code.

**Example (excerpt):**

```
# Categories
Official, Unofficial, Live, Outtakes

# Templates
Live: {date} - {city} - {venue} - {tracknum} {title} [{source}]{lineage_short}
Outtakes: {era}/{session_date} - {title}
Official: {album}/{tracknum} {title}
```

### Flow (6 steps)

1. Extract duration/tags + parse filename.
2. Fingerprint → AcoustID; fetch MB candidates via `musicbrainzngs`.
3. PrinceVault join (SQLite) by date/venue/title alias.
4. **LLM normalize (always)** using compact JSON + naming rules → best proposal + up to 2 alternates.
5. **Review**: show minimal **diff table** (current vs proposed) and alternates.
6. **Approve** → **pre-apply duplicate check** (audio hash) → apply in **Tag‑only** or **Copy+Place**; else mark **Unresolved** (optionally quarantine).

### CLI

* `tagger FILE [--tag-only|--copy-place] [--prefs PATH] [--quarantine PATH]`
* `tagger DIR --batch` (per‑file prompt; **no auto‑apply**)
* Keys: `[Enter]=approve  [a]=alternate  [d]=toggle diff  [e]=edit fields  [pv]=search PV  [s]=skip`

### Config (tiny)

```yaml
paths: { root: "/Volumes/Music/Prince", pv_sqlite: "~/data/princevault/pv.sqlite" }
behavior: { tag_only: true, copy_files: false, write_tags: true, ask_confirmation: true }
llm: { provider: openai, model: gpt-5, temperature: 0.2, max_tokens: 400 }
```

### MVP Milestones

1. Extract + fingerprint + MB lookup + PV join; write **Tag‑only**.
2. LLM proposal + approve/apply flow (single file).
3. Batch mode + **Copy+Place** option.

### Done =

* Correct identification ≥ 80% on known recordings.
* Manual edits required on < 30% of files.
* Originals preserved by default; Tag‑only as the standard mode.

---

## 1) One‑liner

Simple CLI tool (macOS-first) that fingerprints an audio file, fuses AcoustID/MusicBrainz + existing tags + filename + a local PrinceVault mirror, then proposes normalized tags and a canonical destination. **LLM always normalizes/decides**, but **you approve before apply**. The tool supports two apply modes: **Tag‑only** (write tags in place, no rename/move) or **Copy+Place** (copy to destination and tag the copy). Folder & filename rules live in a **plain‑text prefs file** that is passed to the LLM so you can change them without code.

---

## 2) Goals & Non‑Goals

**Goals**

* **LLM‑first approach**: Let AI handle complex pattern recognition instead of brittle regex/rules.
* **Simplicity‑first**: minimal surface area; do the few important things well.
* Identify each track with high confidence using fingerprint + metadata fusion.
* Normalize tags and filenames to a consistent personal spec (bootlegs/live‑friendly).
* Fast confirm/apply loop (Enter=apply, e=edit, s=skip); **always user‑approved**.
* **Non‑destructive** by default: copy to destination; originals remain.
* **Incremental development**: working functionality at each phase.

**Non‑Goals**

* Complex filename parsing logic (let the LLM handle this).
* Hand‑coded fuzzy matching algorithms (let the LLM handle this).
* Bulk "entire library re‑org" without user approval.
* Persistent manifests/undo systems or complex logging.
* Cloud upload of audio or web scraping beyond AcoustID/MusicBrainz APIs.

---

## 3) Success Metrics (personal)

* **Correct identification ≥ 80%** on known recordings.
* **Manual edits required < 30%** of files.

---

## 4) User Stories (lean)

* “As me, when I drop a random Prince track on the tool, I get a confident match proposal with clean tags and a suggested destination path in under a minute.”
* “As me, I can override anything before applying (tags, path, filename).”
* “As me, I can run in **dry‑run** to preview all changes and export a manifest.”

---

## 5) Inputs & Outputs

**Inputs**

* One or more audio files (**MP3, FLAC**; WAV/AIFF/M4A/ALAC optional later).
* Local PrinceVault mirror: **SQLite** (primary) and/or XML (optional fallback).
* API keys: **AcoustID** (Chromaprint) and MusicBrainz user agent.
* YAML preferences (see §10) **plus** a plain‑text naming rules file that the LLM ingests.

**Outputs**

* **Tag‑only mode**: tags written **in place** on the original; no rename/move.
* **Copy+Place mode**: a **copied** file at the proposed destination with updated tags; original untouched.
* Console summary only (no persistent manifest or run logs).

---

## 6) Data Sources

* **AcoustID**: fingerprint → candidate MBIDs + titles/recordings.
* **MusicBrainz**: lookup MBIDs for recording/release/artist credits, dates, disambiguation, relationships.
* **Existing file tags**: title, artist, album, track, date, TXXX custom tags.
* **Filename clues**: e.g., `1986-09-09 Detroit - Purple Rain (SBD).flac`.
* **PrinceVault (local)**: concerts (date/venue/city/tour/setlist), studio recording sessions, known circulating sources, aliases.

---

## 7) Canonical Tag Schema (bootleg/live‑friendly)

**Core**: `Artist, Title, RecordingDate, RecordingPlace, City, State/Region, Country, Venue, Tour, SourceType (SBD/AUD/FM/TV/PRO), Generation/Lineage, Release/BootlegName, Disc/TrackNumber, Duration, MBIDs (Recording, Release, Work), AcoustID, PV_Concert_ID, PV_Recording_ID, Taper, Transfer, Notes`

**Mappings by container**

* **MP3 (ID3v2.3/2.4)**: `TPE1, TIT2, TDRC, TCON(optional), TALB, TRCK, TPOS, TXXX:PVTour, TXXX:PVConcertID, TXXX:Lineage, COMM, UFID:musicbrainz, TXXX:AcoustID, TDRL if needed`.
* **FLAC/Vorbis**: `ARTIST, TITLE, DATE, ALBUM, TRACKNUMBER, DISCNUMBER, LOCATION, VENUE, CITY, COUNTRY, SOURCE, LINEAGE, MUSICBRAINZ_RECORDINGID, ACOUSTID, COMMENTS`.
* **MP4/M4A**: iTunes atoms equivalents + `----:com.apple.iTunes:TXXX` custom.

---

## 8) Folder & Filename Rules

**Root**: `/Prince/Live & Sessions/<YEAR>/<YYYY‑MM‑DD> <City> – <Venue> [<SourceType>]/`

* Studio outtakes: `/Prince/Studio Outtakes/<Era or Year>/`
* Compilations: `/Prince/Mixes & Compilations/<Compiler>/<SetName>/`

**Filename template**

```
<YYYY‑MM‑DD> - <City> - <Venue> - <NN> <Normalized Title> [<SourceType>][<Gen/Lineage short>].<ext>
```

* `NN` is 2‑digit track number if known; otherwise omit.
* Only ASCII letters/nums, space, `-`, `_`, `()`, `[]`. Replace `/\\:*?"<>|` with `_`.
* Collapse multiple spaces, trim.

---

## 9) Resolution Pipeline (LLM‑first, simplified)

1. **Extract**: File metadata (duration, bitrate, existing tags), raw filename (no parsing).
2. **Fingerprint**: Chromaprint → AcoustID → candidate MBIDs + confidence scores.
3. **MusicBrainz**: Fetch candidate recordings/releases for each MBID.
4. **PrinceVault join**: SQLite queries against local database copy.
5. **LLM normalize (always)**: Send **all raw data** + **naming rules text** → LLM decides best match, normalizes metadata, suggests tags + destination path.
6. **Propose**: Display LLM's primary recommendation + alternates in clean diff format.
7. **User approval**: Interactive review with options to approve, edit, choose alternates, or skip.
8. **Pre‑apply safety**: Audio hash check for duplicates at destination.
9. **Apply**: Tag‑only (modify in place) or Copy+Place (copy to destination then tag).
10. **Unresolved**: Files with no confident match go to quarantine folder (optional).

**Key simplification**: No complex filename parsing logic, no hand‑coded fuzzy matching. The LLM handles all pattern recognition, normalization, and decision‑making using the human‑readable naming rules.

---

## 10) Config (YAML)

```yaml
paths:
  root: "/Volumes/Music/Prince"
  category_roots:
    official: "Official"
    unofficial: "Unofficial"
    live: "Live"
    outtakes: "Outtakes"
  logs: null            # no persistent logs
  pv_sqlite: "~/data/princevault/pv.sqlite"
  pv_xml_dir: "~/data/princevault/xml"   # optional
behavior:
  tag_only: false         # if true: write tags in place; no rename/move/copy
  copy_files: true        # if true and tag_only=false: Copy+Place mode
  move_files: false       # never move by default (simplicity)
  write_tags: true        # write tags to the chosen target (in-place or copy)
  ask_confirmation: true  # always require approval
  llm_always: true        # LLM runs on every file
  min_auto_score: null    # no auto-apply thresholds
naming:
  rules_file: "prefs/naming.md"   # human-editable text ingested by LLM
  rules_format: "text"            # can be md/txt; LLM treats as instructions
  templates_default:
    live: "{date} - {city} - {venue} - {tracknum} {title} [{source}]{lineage_short}"
    outtake: "{era}/{session_date} - {title}"
    official: "{album}/{tracknum} {title}"
    unofficial: "{setname}/{tracknum} {title}"
fields:
  keep_custom_tags: ["LINEAGE","TAPER","TRANSFER"]
  prefer_dates_from: ["PrinceVault","MusicBrainz","FileTags"]
api:
  acoustid_key: "env:ACOUSTID_KEY"
  musicbrainz_user_agent: "PrinceTagger/0.3 (you@example.com)"
llm:
  provider: "openai"
  model: "gpt-5"            # placeholder
  temperature: 0.2
  max_tokens: 400
  approval_required: true
  system_prompt: "Normalize metadata and destination per provided prefs and naming rules; return strict JSON; never guess beyond given sources."
```

---

## 11) CLI Flows (simple)

* `tagger FILE` → pipeline → best proposal + alternates + **diff table** → `[Enter]=approve/apply  [--tag-only]=in‑place tags  [e]=edit  [a]=choose alternate  [d]=toggle diff  [pv]=search PV  [s]=skip`
* `tagger DIR --batch` → iterate files; per‑file prompt; **no bulk auto‑apply**.
* Flags: `--tag-only`, `--copy-place`, `--prefs PATH`, `--quarantine PATH` (copy unresolved to holding folder).
* On approve: tool performs **audio‑hash duplicate check** before writing.

---

## 12) LLM Contract (JSON in/out)

**Input (all raw data, no pre-processing)**

```json
{
  "context": {
    "file": {
      "path": "testfiles/1984-08-03 First Avenue Purple Rain [SBD].flac",
      "filename": "1984-08-03 First Avenue Purple Rain [SBD]",
      "extension": ".flac",
      "duration_sec": 296,
      "bitrate": 1411,
      "sample_rate": 44100
    },
    "existing_tags": {
      "TITLE": "Purple Rain", 
      "ARTIST": "Prince",
      "DATE": "1984"
    },
    "acoustid": {
      "fingerprint_id": "acX", 
      "score": 0.92, 
      "mb_recording_ids": ["mbR1", "mbR2"]
    },
    "musicbrainz_data": {
      "recordings": [
        {"id": "mbR1", "title": "Purple Rain", "disambiguation": "live, 1983-08-03, First Avenue"}
      ]
    },
    "princevault_data": {
      "concerts": [
        {"pv_id": 1234, "date": "1983-08-03", "venue": "First Avenue", "city": "Minneapolis", "setlist": ["Purple Rain"]}
      ]
    },
    "naming_rules": "(full contents of config/naming_rules.md)"
  }
}
```

**Key change**: Raw filename and all data sources provided as-is. No tokenization, no pre-parsing. Let the LLM figure out patterns.

**Output (proposed decision)**

```json
{
  "decision": {
    "confidence": 0.91,
    "recording": {"title": "Purple Rain","date": "1983-08-03","city": "Minneapolis","venue": "First Avenue","source": "SBD","pv_concert_id": 1234,"mb_recording_id": "mbR1"},
    "tags": {"ARTIST": "Prince","TITLE": "Purple Rain","DATE": "1983-08-03","VENUE": "First Avenue","CITY": "Minneapolis","SOURCE": "SBD","MUSICBRAINZ_RECORDINGID": "mbR1","ACOUSTID": "acX"},
    "path": "Live/1983/1983-08-03 Minneapolis – First Avenue [SBD]/",
    "filename": "1983-08-03 - Minneapolis - First Avenue - 01 Purple Rain [SBD].flac",
    "notes": ["Title normalized"],
    "action": "propose"
  }
}
```

---

## 13) Tech Stack

* **Language**: Python 3.11+ (**macOS primary target**)
* **CLI**: Typer; Rich tables for diff display
* **Audio/Tags**: `mutagen`
* **Fingerprint**: `pyacoustid` + system `chromaprint`
* **MusicBrainz**: `musicbrainzngs` client (handles auth, rate limits, retries)
* **HTTP**: `httpx` for any auxiliary calls (cache/backoff)
* **DB**: `sqlite3` for PV mirror (primary)
* **Fuzzy**: `rapidfuzz` for titles/venues; `python-dateutil` for dates
* **MediaWiki parsing (optional)**: `mwparserfromhell` if XML fallback is ever needed
* **Config**: plain YAML + text rules file for naming
* **Tests**: `pytest` + tiny fixtures

---

## 14) Safety & Non‑Destructive Design

* **Copy‑only by default**; originals remain untouched.
* No persistent manifests or run logs; console summary only.
* **Duplicate detection** by audio stream hash; avoid creating dupes in destination.
* Optional `--quarantine PATH` to copy **Unresolved** items to a holding folder.

---

## 15) Error Handling & Edge Cases

* No AcoustID match → fall back to tags+filename+PV heuristics.
* Multiple PV concerts same date (e.g., late show) → prompt to choose; show setlists.
* Medleys / tracks split differently between sources → allow `PART` tags.
* Mismatched durations (>±5s) → downgrade score unless PV notes indicate speed/pitch variance.
* Duplicate detection: hash of audio stream; warn before overwriting existing dest.
* Read‑only files / permission errors → skip and log.

---

## 16) Privacy & Rate Limits

* Never send audio to LLM or external services; only fingerprints/metadata.
* Respect MusicBrainz rate limits, use backoff and caching (on‑disk JSON cache).

---

## 17) Testing Plan (fixtures)

* Known iconic shows (e.g., 1983‑08‑03 First Avenue) with multiple circulating sources.
* Studio outtake with many alias titles.
* Corrupt or minimal tags.
* Filename only match.
* Ambiguous two‑candidate case to exercise LLM.

---

## 18) Roadmap (MVP → nice‑to‑have)

**MVP**

* Single‑file flow with confirm/apply, manifest, dry‑run, AcoustID+MB+PV join.
* YAML config, caching, undo.

**Nice‑to‑have**

* Batch mode with per‑file confirmation queue.
* Interactive PV browser pane (search by date/venue/alias).
* Simple HTTP server to act as a drop‑zone UI on localhost.
* Export to .cue / .md5 / lineage notes sidecars.

---

## 19) Diagram (flow)

```mermaid
flowchart TD
  A[File input] --> B[Extract: tags/filename/duration]
  B --> C[Chromaprint → AcoustID]
  C --> D[MusicBrainz lookups]
  B --> E[PrinceVault join (SQLite)]
  D --> F[Fuse evidence + score]
  E --> F
  F --> K[LLM normalize & decide (always)]
  K --> G[Proposed decision + alternates]
  G --> |Approve (Tag-only)| L1[Write tags in place]
  G --> |Approve (Copy+Place)| L2[Copy to dest + write tags]
  G --> |Edit/Alternate| K
  G --> |Skip| M[Unchanged]
