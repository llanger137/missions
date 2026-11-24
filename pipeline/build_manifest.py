#!/usr/bin/env python3
"""Build manifest.json: recent processed images from active space missions.

Phase 1 sources (all curated by people, so no scoring yet):
  - NASA science.nasa.gov galleries for Webb, Hubble and Roman (WordPress API)
  - NASA Photojournal (same API), minus ground hardware and Earth-science
  - ESA/Webb picture of the month and ESA/Hubble picture of the week

Images are not rehosted. Each item points at a TV-sized rendition on the
publisher's own CDN, so the manifest is the only thing this pipeline publishes.

Standard library only. Usage:
  python3 build_manifest.py --out site/manifest.json [--previous URL_OR_FILE]
"""

import argparse
import datetime as dt
import email.utils
import html
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

UA = "missions-tv-feed/1.0 (+https://github.com/llanger137/missions)"
TIMEOUT = 40

TV_W, TV_H = 1920, 1080   # rendition requested for display
THUMB = 384               # rendition for future LLM scoring

# Newest N items kept per source after merging with the previous manifest.
KEEP_PER_SOURCE = {"webb": 40, "hubble": 40, "roman": 40,
                   "photojournal": 80, "esawebb": 12, "esahubble": 20}

NASA_GALLERIES = {"webb": 895905, "hubble": 895902, "roman": 1217464}

# Photojournal posts are ordinary WordPress posts in this category. (Its
# per-gallery RSS feeds all return the same latest 10, so they're no use.)
PJ_CATEGORY = 19797
# Photojournal category slugs that aren't imagery from a mission in flight.
# Earth science and ISS are out of scope (the Earth app covers Earth).
PJ_SKIP_CATEGORIES = {"photojournal", "neo-surveyor", "deep-space-network",
                      "maia", "skyfall", "meteors-meteorites", "nisar",
                      "incus", "cold-atom-laboratory", "sentinel-6b",
                      "sentinel-6-michael-freilich", "international-space-station",
                      "earth"}
MISSION_NAMES = {
    "mars-2020-perseverance": "Perseverance", "curiosity-rover": "Curiosity",
    "mars-science-laboratory": "Curiosity", "juno": "Juno",
    "europa-clipper": "Europa Clipper", "mars-reconnaissance-orbiter": "MRO",
    "lunar-reconnaissance-orbiter": "LRO", "parker-solar-probe": "Parker",
    "new-horizons": "New Horizons", "osiris-apex": "OSIRIS-APEX",
    "psyche-mission": "Psyche", "spherex": "SPHEREx",
}
# Roman's gallery holds pre-launch context images; keep real ones only.
ROMAN_FIRST_LIGHT = "2026-09-01"

ESA_FEEDS = {
    "esawebb": ("Webb", "https://esawebb.org/images/potm/feed/"),
    "esahubble": ("Hubble", "https://esahubble.org/images/potw/feed/"),
}

# Words in a slug or title that mark an item as not a real image.
JUNK_WORDS = re.compile(
    r"artist|illustration|concept|infographic|spectr|diagram|chart|graph|"
    r"compass|north-up|north up|side-by-side|comparison|video|animation|"
    r"\bmap\b|map-|mapping|timeline|labeled|annotated|poster|logo|"
    r"montage|\bifu\b|\bteam\b|ribbon|inspect|testing|clean room|"
    r"assembl|comparing|postcard",
    re.I)
JUNK_TAGS = ("artist-concept", "infographic", "spectra", "videos",
             "animation", "side-by-side", "explainer")


# --------------------------------------------------------------------- utils

def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read()


def fetch_json(url):
    return json.loads(fetch(url))


def text(s, limit=None):
    """HTML fragment -> plain text."""
    s = re.sub(r"<[^>]+>", " ", s or "")
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s).strip()
    s = s.replace("[…]", "…").replace("[&hellip;]", "…")
    if limit and len(s) > limit:
        s = s[:limit].rsplit(" ", 1)[0] + "…"
    return s


def iso(d):
    return d.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def resized(url, w, h):
    """A rendition from NASA's dynamic image server."""
    base = url.split("?", 1)[0]
    return f"{base}?w={w}&h={h}&fit=clip"


def log(*a):
    print(*a, file=sys.stderr)


# --------------------------------------------------- NASA (science.nasa.gov)

WP = "https://science.nasa.gov/wp-json/wp/v2/"
POST_FIELDS = "id,date_gmt,slug,link,title,excerpt,featured_media,class_list"


def wp_tags(post, prefix):
    return [c[len(prefix):] for c in post.get("class_list", [])
            if c.startswith(prefix)]


def wp_media(ids):
    """featured_media id -> media record, fetched 100 at a time."""
    out, ids = {}, sorted(set(i for i in ids if i))
    for k in range(0, len(ids), 100):
        chunk = ids[k:k + 100]
        url = WP + "media?" + urllib.parse.urlencode({
            "include": ",".join(map(str, chunk)), "per_page": 100,
            "_fields": "id,source_url,mime_type,media_details.width,"
                       "media_details.height,nasa_hds_core_meta_image_credit"})
        for m in fetch_json(url):
            out[m["id"]] = m
    return out


def wp_items(posts, source, mission_of):
    """Posts that survived filtering -> manifest items."""
    media = wp_media(p["featured_media"] for p in posts)
    items = []
    for p in posts:
        m = media.get(p["featured_media"])
        if not m or not str(m.get("mime_type", "")).startswith("image/"):
            continue
        md = m.get("media_details") or {}
        w, h = md.get("width") or 0, md.get("height") or 0
        if w and h and min(w, h) < 600:
            continue   # too small for a TV
        src = m["source_url"]
        if "/dynamicimage/" not in src:
            continue   # can't ask for a TV-sized rendition
        items.append({
            "id": f"{source}:{p['id']}",
            "source": source,
            "mission": mission_of(p),
            "kind": "processed",
            "title": text(p["title"]["rendered"]),
            "description": re.sub(r"^Description\s+", "",
                                  text(p["excerpt"]["rendered"], 400)),
            "date": p["date_gmt"] + "Z",
            "credit": text(m.get("nasa_hds_core_meta_image_credit") or ""),
            "page": p["link"],
            "image": resized(src, TV_W, TV_H),
            "thumb": resized(src, THUMB, THUMB),
            "width": w, "height": h,
        })
    return items


def is_junk(post):
    title = text(post["title"]["rendered"])
    return bool(JUNK_WORDS.search(post["slug"]) or JUNK_WORDS.search(title))


def nasa_gallery(source, parent):
    """Webb / Hubble / Roman galleries on science.nasa.gov."""
    posts = fetch_json(WP + "stma?" + urllib.parse.urlencode({
        "parent": parent, "per_page": 100, "_fields": POST_FIELDS}))

    kept, groups = [], set()
    for p in posts:
        tags = wp_tags(p, "science-org-")
        if any(j in t for t in tags for j in JUNK_TAGS) or is_junk(p):
            continue
        if source == "roman" and p["date_gmt"] < ROMAN_FIRST_LIGHT:
            continue
        # A release posts several near-duplicates on one day ("X (NIRCam)",
        # "X (MIRI)", "X, North Up"). Keep the first of each title stem.
        title = text(p["title"]["rendered"])
        stem = re.split(r"[(,:]", title.lower())[0].strip()
        key = (p["date_gmt"][:10], stem)
        if key in groups:
            continue
        groups.add(key)
        kept.append(p)

    name = {"webb": "Webb", "hubble": "Hubble", "roman": "Roman"}[source]
    return wp_items(kept, source, lambda p: name)


def photojournal():
    posts = fetch_json(WP + "posts?" + urllib.parse.urlencode({
        "categories": PJ_CATEGORY, "per_page": 60, "_fields": POST_FIELDS}))

    def missions(p):
        return [c for c in wp_tags(p, "category-")
                if c not in PJ_SKIP_CATEGORIES]

    kept = [p for p in posts
            if missions(p)
            and not set(wp_tags(p, "category-")) & PJ_SKIP_CATEGORIES - {
                "photojournal"}
            and not is_junk(p)]

    def mission_of(p):
        c = missions(p)[0]
        return MISSION_NAMES.get(c, c.replace("-", " ").title())

    return wp_items(kept, "photojournal", mission_of)


# ------------------------------------------------------------------------ ESA

def rss_items(xml):
    """Small regex RSS reader (tolerates feeds that aren't valid XML)."""
    for block in re.findall(r"<item>(.*?)</item>", xml, re.S):
        def field(tag, block=block):
            m = re.search(rf"<{tag}[^>]*>(.*?)</{tag}>", block, re.S)
            if not m:
                return ""
            v = m.group(1).strip()
            v = re.sub(r"^<!\[CDATA\[(.*)\]\]>$", r"\1", v, flags=re.S)
            return v.strip()
        enc = re.search(r'<enclosure[^>]*url="([^"]+)"', block)
        yield {"title": field("title"), "link": field("link"),
               "description": field("description"),
               "pubDate": field("pubDate"),
               "enclosure": enc.group(1) if enc else ""}


def rss_date(s):
    d = email.utils.parsedate_to_datetime(s)
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return iso(d)


def esa(source):
    mission, url = ESA_FEEDS[source]
    items = []
    for it in rss_items(fetch(url).decode("utf-8")):
        enc = it["enclosure"]
        if "/archives/images/screen/" not in enc:
            continue   # comparisons and other non-image entries
        title = text(it["title"])
        if not title or JUNK_WORDS.search(title):
            continue
        name = enc.rsplit("/", 1)[-1].rsplit(".", 1)[0]
        items.append({
            "id": f"{source}:{name}",
            "source": source,
            "mission": mission,
            "kind": "processed",
            "title": title,
            # ESA's feed description is just "potm2611 - <title>".
            "description": "",
            "date": rss_date(it["pubDate"]),
            "credit": "ESA/Webb" if source == "esawebb" else "ESA/Hubble",
            "page": it["link"],
            # wallpaper4 is 1920 wide; screen is 1280.
            "image": enc.replace("/screen/", "/wallpaper4/"),
            "thumb": enc.replace("/screen/", "/thumb700x/"),
        })
    return items


# ---------------------------------------------------------------------- build

def load_previous(where):
    if not where:
        return []
    try:
        if re.match(r"https?://", where):
            data = json.loads(fetch(where))
        else:
            with open(where) as f:
                data = json.load(f)
    except urllib.error.HTTPError as e:
        if e.code == 404:
            log("previous manifest: none yet (404), starting fresh")
            return {}
        raise
    except FileNotFoundError:
        log("previous manifest: no file, starting fresh")
        return {}
    return data


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--previous", help="URL or path of the last manifest")
    args = ap.parse_args()

    jobs = [(s, lambda s=s, p=p: nasa_gallery(s, p))
            for s, p in NASA_GALLERIES.items()]
    jobs += [("photojournal", photojournal)]
    jobs += [(s, lambda s=s: esa(s)) for s in ESA_FEEDS]

    fresh, failed = [], []
    for name, job in jobs:
        try:
            got = job()
            log(f"{name}: {len(got)} items")
            fresh += got
        except Exception as e:   # one broken source mustn't sink the rest
            log(f"{name}: FAILED {type(e).__name__}: {e}")
            failed.append(name)

    if len(failed) == len(jobs):
        sys.exit("every source failed; not writing a manifest")

    # Merge: fresh wins over previous for the same id; previous items keep
    # sources whose feeds only show their last 10 entries populated.
    previous = load_previous(args.previous)
    by_id = {it["id"]: it for it in previous.get("items", [])}
    by_id.update({it["id"]: it for it in fresh})

    # Same picture published by two galleries (e.g. a joint Hubble/Webb
    # release): keep one.
    seen_img, merged = set(), []
    for it in sorted(by_id.values(), key=lambda x: x["date"], reverse=True):
        key = it["image"].split("?", 1)[0]
        if key in seen_img:
            continue
        seen_img.add(key)
        merged.append(it)

    counts, items = {}, []
    for it in merged:
        n = counts.get(it["source"], 0)
        if n < KEEP_PER_SOURCE.get(it["source"], 40):
            items.append(it)
            counts[it["source"]] = n + 1

    # Leave the file alone when nothing changed, so the scheduled job only
    # commits when there's something new.
    if (args.out == args.previous and items == previous.get("items")
            and failed == previous.get("failed_sources")):
        log(f"unchanged ({len(items)} items); not rewriting {args.out}")
        return

    manifest = {
        "version": 1,
        "updated": iso(dt.datetime.now(dt.timezone.utc)),
        "failed_sources": failed,
        "counts": counts,
        "items": items,
    }
    with open(args.out, "w") as f:
        json.dump(manifest, f, indent=1, ensure_ascii=False)
    log(f"wrote {len(items)} items to {args.out} {counts}")


if __name__ == "__main__":
    main()
