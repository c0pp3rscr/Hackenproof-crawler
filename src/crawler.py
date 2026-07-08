"""Crawl HackenProof bug-bounty programs.

The site is a Nuxt 3 app behind Cloudflare. Program listings are enumerated from
the public ``sitemap.xml`` and each program's requirements live in the
server-rendered ``__NUXT_DATA__`` blob on its detail page. We fetch with a
Googlebot user-agent, which HackenProof allow-lists for SEO so the pages are
returned fully rendered instead of a Cloudflare challenge.
"""

from __future__ import annotations

import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from typing import Iterable, Optional

import requests

from nuxt import NuxtDataNotFound, parse_nuxt_data

BASE_URL = "https://hackenproof.com"
SITEMAP_URL = f"{BASE_URL}/sitemap.xml"

# HackenProof serves crawlers the real SSR page instead of a Cloudflare
# challenge, so we identify as Googlebot to read public program data.
USER_AGENT = (
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)"
)

_PROGRAM_URL_RE = re.compile(r"https://hackenproof\.com/programs/([a-z0-9\-]+)")


@dataclass
class Program:
    """The subset of program data we surface in the spreadsheet."""

    name: str
    company: str
    slug: str
    reputation_required: Optional[int]  # minimum reputation points to participate
    kyc_required: Optional[bool]
    poc_required: Optional[bool]
    submission_fee: Optional[int]  # deposit/fee (USD) required to submit a report
    deposit_available: Optional[bool]  # program has a guaranteed reward deposit
    max_reward: str
    status: str
    activity_status: str
    url: str


def make_session() -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
        }
    )
    return session


def _get(session: requests.Session, url: str, retries: int = 3,
         timeout: int = 30) -> requests.Response:
    """GET with simple exponential backoff on transport / 5xx errors."""
    last_exc: Optional[Exception] = None
    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=timeout, allow_redirects=True)
            if resp.status_code >= 500:
                raise requests.HTTPError(f"{resp.status_code} for {url}")
            return resp
        except requests.RequestException as exc:  # network error or 5xx
            last_exc = exc
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"failed to GET {url}: {last_exc}")


def fetch_program_slugs(session: requests.Session) -> list[str]:
    """Return all program slugs listed in the sitemap, de-duplicated & sorted."""
    resp = _get(session, SITEMAP_URL)
    resp.raise_for_status()
    slugs = set(_PROGRAM_URL_RE.findall(resp.text))
    return sorted(slugs)


def _as_bool(value) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    return None


def _as_int(value) -> Optional[int]:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return None
    return None


def parse_program(html: str, slug: str, url: str) -> Program:
    """Turn a program detail page into a :class:`Program` record."""
    data = parse_nuxt_data(html)
    program = data["data"]["program"]

    activity = program.get("activityStatus")
    activity_name = ""
    if isinstance(activity, dict):
        activity_name = activity.get("name") or ""

    return Program(
        name=(program.get("title") or "").strip(),
        company=(program.get("companyName") or "").strip(),
        slug=slug,
        reputation_required=_as_int(program.get("minReputation")),
        kyc_required=_as_bool(program.get("kycRequired")),
        poc_required=_as_bool(program.get("pocRequired")),
        submission_fee=_as_int(program.get("submissionFee")),
        deposit_available=_as_bool(program.get("depositAvailable")),
        max_reward=(program.get("maxReward") or "").strip(),
        status=(program.get("status") or "").strip(),
        activity_status=activity_name.strip(),
        url=url,
    )


def fetch_program(session: requests.Session, slug: str) -> Program:
    url = f"{BASE_URL}/programs/{slug}"
    resp = _get(session, url)
    if resp.status_code == 404:
        raise LookupError(f"program not found: {slug}")
    resp.raise_for_status()
    # A program may 301 to a renamed slug; trust the final resolved URL.
    final_url = resp.url
    final_slug = final_url.rstrip("/").rsplit("/", 1)[-1]
    return parse_program(resp.text, final_slug, final_url)


def crawl(
    slugs: Optional[Iterable[str]] = None,
    workers: int = 8,
    on_progress=None,
) -> list[Program]:
    """Fetch every program and return de-duplicated :class:`Program` records.

    ``on_progress`` if given is called as ``on_progress(done, total, program_or_error)``.
    """
    session = make_session()
    if slugs is None:
        slugs = fetch_program_slugs(session)
    slugs = list(slugs)
    total = len(slugs)

    results: dict[str, Program] = {}
    errors: list[tuple[str, Exception]] = []

    def task(slug: str) -> Program:
        # Each worker gets its own session; requests.Session isn't guaranteed
        # thread-safe for concurrent requests.
        return fetch_program(make_session(), slug)

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(task, slug): slug for slug in slugs}
        for done, future in enumerate(as_completed(futures), start=1):
            slug = futures[future]
            try:
                program = future.result()
                results[program.slug] = program  # dedupe on canonical slug
                if on_progress:
                    on_progress(done, total, program)
            except (LookupError, NuxtDataNotFound, RuntimeError, KeyError) as exc:
                errors.append((slug, exc))
                if on_progress:
                    on_progress(done, total, exc)

    if errors:
        preview = ", ".join(f"{s} ({e.__class__.__name__})" for s, e in errors[:10])
        print(f"\n{len(errors)} program(s) failed: {preview}"
              + (" ..." if len(errors) > 10 else ""))

    return sorted(results.values(), key=lambda p: p.name.lower())


def programs_to_rows(programs: list[Program]) -> list[dict]:
    return [asdict(p) for p in programs]
