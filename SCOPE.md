# Missions — TV app scope

Drafted 2026-11-23. A Sony BRAVIA (Google TV) app showing recent imagery from
active space missions, processed and raw. Sibling to White Marble / Luna / Ares
in `~/TV/apps/`.

## The two worries, re-sized

**TV storage is not a real problem.** The earlier pain was installing 50–150 MB
APKs that bundle maps. This app bundles no imagery; it streams JPEGs and keeps
a small rotating disk cache (~100 images at 1080p ≈ 50 MB). Expected APK is
~15–20 MB. No Xbox needed.

**Volume is real, but only for raw feeds.** Two very different tiers:

| Tier | Sources | Volume | Filter needed |
|---|---|---|---|
| Curated | NASA Webb + Hubble galleries (see below), ESA/Webb images feed, ESA Hubble POTW, ESA multimedia (Euclid, BepiColombo, Juice), NASA Images API, Roman releases, APOD | ~10–30 / week total | none — humans already picked them |
| Raw | Perseverance raw API, Curiosity raw API | ~300–500 / sol / rover | yes |
| Raw (hard) | JWST/Euclid archive frames (MAST, ESA) | thousands / day, mostly uncalibrated | skip for v1 |

## Webb and Hubble: NASA's image galleries

The galleries at science.nasa.gov (Webb:
`/mission/webb/multimedia/images/`, Hubble: `/mission/hubble/multimedia/hubble-images/`)
are WordPress, and the open REST API serves them directly. No scraping needed.

- Webb: `https://science.nasa.gov/wp-json/wp/v2/stma?parent=895905&per_page=50`
  (990 items, newest first; three posted today, 2026-11-23).
- Hubble: same call with `parent=895902`.
- Each item has date, title, a description in `excerpt`, and `featured_media`
  (→ `/wp/v2/media/<id>` for the image). `og:image` on the page gives a
  1280 px rendition; the full image is on `assets.science.nasa.gov`.
- Filter with the `science-org-*` tags in `class_list`. **Keep**
  `webb-images-science-release`. **Drop** `artist-concept`, `infographic`,
  `spectra`, `webb-videos`, slugs containing `compass`, and probably
  `side-by-side` (keep the single-telescope versions).
- Releases come in clusters of 2–4 near-duplicates (e.g. normal and "north
  up"), so keep one per release: group by date, prefer `nircam-image` /
  `miri-image`.

This replaces ESA/Webb's RSS as the main Webb source; ESA's stays as a backup
and adds its own picture of the month.

Verified live today: Perseverance raw API (1.06 M images over 2,032 sols),
Curiosity raw API (sol 5083, images from today), ESA/Webb RSS (item dated
today).

## Filtering raw rover images

1. **Metadata pre-filter (free).** Drop engineering/sky cams (SKYCAM, MEDA),
   thumbnails and subframes; keep Mastcam-Z, Navcam, Hazcam, WATSON, MAHLI,
   SHERLOC color; collapse stereo pairs and mosaic sequences to one
   representative. Should cut ~500/sol to ~20–50.
2. **LLM rating on thumbnails.** Send each survivor at ~256 px to a small
   vision model (Haiku) with a short rubric ("would a curious family stop and
   look?"), score 1–10. Small thumbnails are on the order of 100 tokens each,
   so this is cheap — the "don't process whole images" instinct is right, and
   it's enough.
3. Keep top N per sol.

## Where the pipeline runs

Not Google Photos (its API no longer lets an app read images it didn't upload
itself, and it adds nothing here). Instead, the pattern already used for
`luna-data`:

- A **scheduled GitHub Action** (every few hours) polls feeds, filters, calls
  Claude, downloads the winners, resizes to 1920 px, and publishes
  `manifest.json` + JPEGs to a GitHub Pages repo, pruning anything older than
  ~30 days.
- The **TV app** just reads `manifest.json`. All intelligence lives off-device,
  so tuning the filter never needs a TV rebuild.

## TV app (v1)

- Flutter, armeabi-v7a, same build/install recipe as `apps/mars`.
- Full-screen slideshow, slow pan/zoom, caption: mission, instrument, date,
  processed vs raw, one-line description.
- Remote: left/right skip, OK shows details, Back exits.
- Open idea: also ship it as an Android TV **screensaver** (DreamService), and
  exempt it from TV Timer like Earth.

## Mission notes (as of today)

- **BepiColombo** entered Mercury orbit with a glitch, now in safe mode;
  orbiters separate early December; science imagery months away.
- **Roman** launched 2026-08-30; first-light test image out; first science
  images expected December 2026–early 2027.
- **JWST** — ESA/Webb feed is the easy path; raw MAST previews are a v2 idea.
- **Euclid** — periodic ESA releases; no steady stream.
- **Perseverance / Curiosity** — the bulk of daily content.

## Phases

1. Pipeline with curated feeds only → manifest on Pages.
2. TV slideshow reading the manifest.
3. Add rover raw feeds with metadata filter + Claude rating.
4. Screensaver mode, more missions, JWST raw (maybe).

## Phase 1 status (2026-11-24)

Built, run locally, not yet on GitHub.

- `pipeline/build_manifest.py` (stdlib Python) writes `site/manifest.json`;
  `site/index.html` is a browser preview of it. First run: 89 images
  (Webb 16 + ESA/Webb 12, Hubble 18 + ESA/Hubble 11, Photojournal 32:
  Curiosity, Perseverance, Psyche, Juno, MRO, SPHEREx). Runs in ~6 s.
- Images are **not rehosted**. NASA's image server resizes on request
  (`?w=1920&h=1080&fit=clip`), and ESA has a 1920-wide `wallpaper4` size, so the
  manifest points straight at TV-sized files. Some NASA sources are PNG and
  stay PNG (up to ~5 MB).
- Photojournal = WordPress posts in category 19797. Its per-planet RSS feeds
  are broken (all return the same latest 10), so the API is used instead.
  Earth science, ISS and ground hardware are dropped with a category skip list
  plus title words.
- Roman's gallery so far has only pre-launch context images; items before
  2026-09-01 are skipped, so Roman shows up when its first images post.
- `.github/workflows/feed.yml`: every 3 h, rebuild → commit `manifest.json`
  only if the picks changed → deploy `site/` to Pages. The commits also stop
  GitHub disabling the schedule for inactivity (60 days).
- Filtering is keyword-based, so the odd non-photo (people, charts) can slip
  through until the phase 3 scorer exists. Very wide panoramas come through
  as thin strips; the TV app will need to pan them.

Not done in phase 1: ESA's own missions (Euclid, BepiColombo, Juice). esa.int
returned 404/connection errors to the URLs tried; that's two URLs, not the
site, so the ESA multimedia route is still open.

## HiRISE added (2026-11-24)

HiRISE Picture of the Day: one captioned Mars image a day from MRO, about 30 a
month, from `uahirise.org/hipod/archive/` (the RSS feed only carries today's).
Each run reads the archive and fetches only days not already in the manifest.
Images are 2560×1920 JPEGs (~2 MB, no smaller size published). Many feature
older observations, so items carry `taken` alongside the posting `date`.
November yield went from 6 to ~30.

## ESA library added (2026-11-24)

ESA's image library has a JSON search API (`www.esa.int/api/search?category=multimedia&contentType=image`),
about 100 images every 2–3 weeks, mostly launches, people, hardware and Earth
observation. The builder keeps items tied to a science mission (by subject
label or title words) and drops non-photos by title. First run: 17 images, all
real (Euclid, Hera at Didymos, Mars Express, Cluster), about 15 a month.
Resized WebP copies (`fit_large`, ~1660 and ~3320 wide) are linked from each
item's page with a hash in the name, so the builder fetches that page once per
new item. esa.int's certificate chain needs a newer root than this Mac's CA
store has, so the builder uses `certifi`.

This is a title-rule filter; the phase 3 scorer should replace it, since some
good images are missed (subject left blank and no mission word in the title)
and ESA's artist renderings are only caught by wording.
