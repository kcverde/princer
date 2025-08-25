# Prince Tagger Naming Rules

## Categories

**Official**: Commercial releases, official compilations, and authorized recordings
**Live**: Concert recordings from tours, club shows, and live performances  
**Outtakes**: Studio recordings, demos, alternate versions not officially released
**Unofficial**: Bootleg compilations, fan-created collections

## File Templates

### Live Recordings
Format: `{date} - {city} - {venue} - {tracknum:02d} {title} [{source}]{lineage_short}`

Examples:
- `1984-08-03 - Minneapolis - First Avenue - 01 Purple Rain [SBD].flac`
- `1987-03-31 - Detroit - Joe Louis Arena - 05 Sign O The Times [AUD-G2].mp3`

### Studio Outtakes  
Format: `{era}/{session_date} - {title}`

Examples:
- `Purple Rain Era/1983-08-01 - Electric Intercourse (Take 2).flac`
- `1999 Era/1982-04-14 - Moonbeam Levels.mp3`

### Official Releases
Format: `{album}/{tracknum:02d} {title}`

Examples:
- `Purple Rain/01 Let's Go Crazy.mp3`
- `Sign O The Times/12 The Cross.flac`

### Unofficial Compilations
Format: `{setname}/{tracknum:02d} {title}`

Examples:
- `Purple Rain Sessions/03 Computer Blue (Long Version).flac`
- `Vault Rarities Vol 1/08 Possessed.mp3`

## Source Type Codes

- **SBD**: Soundboard recording (direct from mixing console)
- **AUD**: Audience recording (microphones in audience)
- **FM**: Radio broadcast recording  
- **TV**: Television broadcast recording
- **PRO**: Professional recording (multi-track, studio quality)
- **MATRIX**: Mix of soundboard and audience sources
- **VINYL**: Transferred from vinyl record
- **CD**: Transferred from compact disc
- **DAT**: Digital Audio Tape source

## Generation/Lineage Notation

- **G1** or **Gen1**: First generation copy
- **G2** or **Gen2**: Second generation copy  
- **(M)**: Master tape source
- **(A)**: Analog source chain
- **(D)**: Digital source chain

## Venue and Location Rules

- Use official venue names when known
- Include city and state/country for clarity
- Use common abbreviations (NYC, LA, etc.) only for well-known cities
- Format: `City - Venue Name` or `City, State - Venue Name`

## Title Normalization Rules

1. Use standard Prince song titles (check discogs/musicbrainz)
2. Include version info in parentheses: `(Long Version)`, `(Edit)`, `(Live)`
3. For medleys, use format: `Song 1 > Song 2 > Song 3`
4. Keep original punctuation from official releases
5. Use sentence case, not ALL CAPS

## File Path Structure

Root: `/Prince/`

- `/Prince/Official/{Album}/`  
- `/Prince/Live/{Year}/`
- `/Prince/Outtakes/{Era}/`
- `/Prince/Unofficial/{Compilation}/`

## Character Restrictions

- Use only: A-Z, a-z, 0-9, space, hyphen (-), underscore (_), parentheses (), brackets []
- Replace invalid characters: `/\:*?"<>|` with underscore `_`  
- Collapse multiple spaces to single space
- Trim leading/trailing whitespace
- Maximum filename length: 255 characters

## Date Formats

- Primary: `YYYY-MM-DD` (ISO 8601)
- Year only: `YYYY` for studio sessions when exact date unknown
- Era designation: `{Album} Era` for outtakes

## Special Cases

- **Medleys**: List all songs with `>` separator
- **Segues**: Use `>` to show continuous tracks  
- **Multiple shows same date**: Add `(Early Show)` or `(Late Show)`
- **Rehearsals**: Include `(Rehearsal)` in title
- **Soundchecks**: Include `(Soundcheck)` in title
- **Incomplete tracks**: Add `(Incomplete)` or `(Fade In/Out)`

## Quality Indicators

- Include speed corrections: `(Speed Corrected)`
- Note pitch issues: `(Pitch Corrected)`  
- Mark poor quality: `(Low Quality)` in comments, not filename
- Highlight upgrades: `(Upgraded Master)`