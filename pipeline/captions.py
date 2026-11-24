"""Kid-readable captions for manifest items, written by Claude.

Each item gets a `caption`: one or two sentences a 9-year-old can read off
the TV, saying what took the picture, where that spacecraft is, and what
we're looking at. Captions are written once per item and carried forward
from the previous manifest, so a run only pays for new images.

Needs ANTHROPIC_API_KEY (a GitHub secret in CI). Without it, items go out
uncaptioned and the TV falls back to the title.
"""

import concurrent.futures as cf
import os
import re
import sys

MODEL = "claude-opus-5-5"
MAX_PER_RUN = 200     # backlog cap; the first run captions everything
WORKERS = 6
MAX_CHARS = 240       # about three lines on the TV's caption bar

SYSTEM = """You write the caption bar for a TV slideshow of new space \
pictures, read by a 9-year-old. For each picture write ONE or TWO short \
sentences, at most 35 words in all, plain text, no quotes or emoji.

Say which spacecraft or telescope took it and, in a few words, where that \
machine is, then what the picture shows, with one fact that makes it amazing. \
Use everyday words and comparisons a kid knows; no jargon (say "dust and \
gas", not "interstellar medium"; "infrared light we can't see", not "MIRI"). \
Round big numbers. Only state facts that the title, description or picture \
support, plus the well-known basics below. If the description says the photo \
was taken years ago, it's fine not to mention that.

Example, for a Webb picture of the Crab Nebula:
The James Webb Space Telescope, which sits beyond the Moon, shows the \
leftovers of a star that exploded almost 1000 years ago.

Where things are:
- James Webb Space Telescope: in space, about four times farther away than \
the Moon.
- Hubble Space Telescope: circling Earth, just above the air.
- Euclid: an ESA telescope out past the Moon, mapping billions of galaxies.
- Roman Space Telescope: a new NASA telescope out past the Moon.
- Mars Reconnaissance Orbiter (MRO) and its HiRISE camera: circling Mars; \
HiRISE can spot things the size of a kitchen table.
- Curiosity and Perseverance: car-sized robot rovers driving on Mars.
- Mars Express: an ESA spacecraft circling Mars.
- Juno: circling Jupiter. Psyche: flying to a metal asteroid.
- Hera: an ESA spacecraft visiting the asteroid Didymos and its moon \
Dimorphos.
- BepiColombo: at Mercury, the planet closest to the Sun.
- Juice: an ESA spacecraft on its way to Jupiter's icy moons.
- SPHEREx: a NASA telescope circling Earth, mapping the whole sky."""


def _small(url):
    """A rendition small enough to send as a picture (NASA resizes on request)."""
    if "assets.science.nasa.gov/dynamicimage/" in url:
        return url.split("?", 1)[0] + "?w=1024&h=1024&fit=clip"
    return url


def _prompt(it):
    lines = [f"Mission: {it.get('mission', '')}",
             f"Title: {it.get('title', '')}"]
    if it.get("instrument"):
        lines.append(f"Instrument: {it['instrument']}")
    if it.get("target"):
        lines.append(f"Target: {it['target']}")
    if it.get("description"):
        lines.append(f"Description: {it['description']}")
    return "\n".join(lines) + "\n\nWrite the caption."


def _clean(s):
    s = re.sub(r"\s+", " ", s).strip().strip('"“”')
    if len(s) > MAX_CHARS:   # keep whole sentences that fit
        cut = s[:MAX_CHARS]
        end = max(cut.rfind(". "), cut.rfind("! "))
        s = cut[:end + 1] if end > 40 else cut.rsplit(" ", 1)[0] + "…"
    return s


def _caption(client, anthropic, it):
    image = {"type": "image",
             "source": {"type": "url", "url": _small(it["thumb"] or it["image"])}}
    text = {"type": "text", "text": _prompt(it)}
    for content in ([image, text], [text]):   # text-only if the image won't load
        try:
            resp = client.beta.messages.create(
                model=MODEL,
                max_tokens=2000,
                system=SYSTEM,
                output_config={"effort": "low"},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                messages=[{"role": "user", "content": content}],
            )
        except anthropic.BadRequestError as e:
            if content[0] is image:
                print(f"  caption {it['id']}: image refused ({e.message}); "
                      "retrying text-only", file=sys.stderr)
                continue
            raise
        if resp.stop_reason == "refusal":
            return None
        out = "".join(b.text for b in resp.content if b.type == "text")
        return _clean(out) or None
    return None


def add_captions(items, previous_items):
    """Carry old captions forward, then write new ones. Mutates items."""
    old = {it["id"]: it["caption"] for it in previous_items if it.get("caption")}
    for it in items:
        if it["id"] in old and not it.get("caption"):
            it["caption"] = old[it["id"]]

    todo = [it for it in items if not it.get("caption")][:MAX_PER_RUN]
    if not todo:
        return 0
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print(f"captions: {len(todo)} uncaptioned, no ANTHROPIC_API_KEY; "
              "skipping", file=sys.stderr)
        return 0
    import anthropic
    client = anthropic.Anthropic(max_retries=4)

    done = 0
    with cf.ThreadPoolExecutor(WORKERS) as pool:
        futs = {pool.submit(_caption, client, anthropic, it): it for it in todo}
        for f in cf.as_completed(futs):
            it = futs[f]
            try:
                cap = f.result()
            except anthropic.AuthenticationError:
                print("captions: API key rejected; stopping", file=sys.stderr)
                pool.shutdown(cancel_futures=True)
                break
            except anthropic.APIError as e:   # one failure mustn't sink the run
                print(f"  caption {it['id']}: FAILED {type(e).__name__}: {e}",
                      file=sys.stderr)
                continue
            if cap:
                it["caption"] = cap
                done += 1
    print(f"captions: wrote {done} of {len(todo)}", file=sys.stderr)
    return done
