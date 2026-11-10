
import argparse
import csv
import json
import logging
import re
import sys
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

LOG_FILE = "scraper.log"
USER_AGENT = "SYNTECXHUB-HeadlineScraper/1.0 (educational project)"
TIMEOUT = 15


SELECTORS = [
    "span.titleline > a",    
    "a.titlelink",           
    "a.storylink",            
    "h1 a, h2 a, h3 a",     
    "article a",             
]

DEFAULT_SOURCES = ["https://news.ycombinator.com/"]


def setup_logging() -> logging.Logger:
    logger = logging.getLogger("headlines_scraper")
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s",
                            datefmt="%Y-%m-%d %H:%M:%S")
    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(fmt)
    logger.addHandler(console)
    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setFormatter(fmt)
    logger.addHandler(file_handler)
    return logger


def fail(logger: logging.Logger, message: str) -> "SystemExit":
    logger.error(message)
    print(f"ERROR: {message}", file=sys.stderr)
    print("See scraper.log for details.", file=sys.stderr)
    raise SystemExit(1)


def robots_allows(url: str, logger: logging.Logger) -> bool:
    """True if robots.txt allows this scraper on the URL (or has no rules)."""
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        parser.read()
    except Exception as exc:
        logger.warning("Could not read %s (%s) — proceeding cautiously",
                       robots_url, exc)
        return True
    allowed = parser.can_fetch(USER_AGENT, url)
    if not allowed:
        logger.warning("robots.txt disallows scraping %s — skipping", url)
    return allowed


def fetch(url: str, logger: logging.Logger) -> str:
    try:
        resp = requests.get(url, headers={"User-Agent": USER_AGENT},
                            timeout=TIMEOUT)
        resp.raise_for_status()
    except requests.exceptions.Timeout:
        raise RuntimeError(f"Timed out after {TIMEOUT}s")
    except requests.exceptions.HTTPError as exc:
        raise RuntimeError(f"HTTP {exc.response.status_code}")
    except requests.exceptions.RequestException as exc:
        raise RuntimeError(f"Request failed: {exc}")
    return resp.text


def find_time(link) -> str:
    """Best-effort time for a headline link: <time datetime>, or a nearby
    element whose class hints at a date (e.g. Hacker News span.age)."""
    time_tag = link.find("time")
    if time_tag and time_tag.get("datetime"):
        return time_tag["datetime"].strip()
    parent = link.parent
    for _ in range(3):
        if parent is None:
            break
        for candidate in parent.find_all(["span", "time"], limit=8):
            classes = " ".join(candidate.get("class", [])).lower()
            if any(word in classes for word in ("time", "age", "date")):
                text = candidate.get_text(strip=True)
                if text:
                    return text
        parent = parent.parent
    # Some layouts (e.g. Hacker News) put the time in the next table row.
    row = link.find_parent("tr")
    if row is not None:
        nxt = row.find_next_sibling("tr")
        if nxt is not None:
            age = nxt.select_one(".age, time")
            if age is not None:
                text = age.get_text(strip=True)
                if text:
                    return text
    return ""


def parse_headlines(html: str, base_url: str, limit: int,
                    logger: logging.Logger) -> list:
    soup = BeautifulSoup(html, "html.parser")
    seen, headlines = set(), []
    for selector in SELECTORS:
        links = soup.select(selector)
        for link in links:
            title = link.get_text(strip=True)
            href = link.get("href", "").strip()
            if len(title) < 10 or not href or href.startswith("#"):
                continue
            url = urljoin(base_url, href)
            if url in seen:
                continue
            seen.add(url)
            headlines.append({
                "title": title,
                "url": url,
                "time": find_time(link),
                "source": urlparse(base_url).netloc,
            })
            if len(headlines) >= limit:
                break
        if headlines:
            logger.info("Parsed %d headline(s) from %s using selector %r",
                        len(headlines), base_url, selector)
            break
    if not headlines:
        logger.warning("No headlines found on %s — the site layout may "
                       "have changed", base_url)
    return headlines


def scrape_source(url: str, limit: int, logger: logging.Logger) -> list:
    if not robots_allows(url, logger):
        return []
    html = fetch(url, logger)
    return parse_headlines(html, url, limit, logger)


def save(headlines: list, output: Path, fmt: str, logger: logging.Logger) -> None:
    if fmt == "json":
        output.write_text(json.dumps(headlines, indent=2, ensure_ascii=False),
                          encoding="utf-8")
    else:
        with output.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["title", "url", "time", "source"])
            writer.writeheader()
            writer.writerows(headlines)
    logger.info("Saved %d headline(s) to %s", len(headlines), output)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Scrape headlines from news websites and save them.")
    parser.add_argument("--url", action="append", default=[],
                        help="News page to scrape (repeatable; "
                             "default: Hacker News front page)")
    parser.add_argument("--output", default="headlines.json",
                        help="Output file (default: headlines.json)")
    parser.add_argument("--format", choices=["json", "csv"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--keyword", action="append", default=[],
                        help="Only keep headlines containing this word "
                             "(case-insensitive, repeatable)")
    parser.add_argument("--limit", type=int, default=20,
                        help="Max headlines per source (default: 20)")
    parser.add_argument("--delay", type=float, default=2.0,
                        help="Seconds to wait between sources (default: 2)")
    parser.add_argument("--no-robots-check", action="store_true",
                        help="Skip the robots.txt check (not recommended)")
    args = parser.parse_args(argv)

    logger = setup_logging()
    sources = args.url or DEFAULT_SOURCES
    output = Path(args.output)

    if args.limit < 1:
        fail(logger, "--limit must be at least 1")
    if args.format == "csv" and output.suffix.lower() != ".csv":
        logger.warning('Output "%s" does not end in .csv — writing CSV anyway',
                       args.output)
    if args.format == "json" and output.suffix.lower() != ".json":
        logger.warning('Output "%s" does not end in .json — writing JSON anyway',
                       args.output)

    all_headlines, failed = [], []
    for i, url in enumerate(sources):
        if i > 0:
            time.sleep(args.delay)
        logger.info("Scraping %s ...", url)
        try:
            if args.no_robots_check:
                html = fetch(url, logger)
                headlines = parse_headlines(html, url, args.limit, logger)
            else:
                headlines = scrape_source(url, args.limit, logger)
            all_headlines.extend(headlines)
        except RuntimeError as exc:
            logger.error("Failed to scrape %s: %s", url, exc)
            failed.append(url)

    if args.keyword:
        # Whole-word match, so --keyword AI does not match "Ghanaian".
        patterns = [re.compile(r"\b" + re.escape(k) + r"\b", re.IGNORECASE)
                    for k in args.keyword]
        before = len(all_headlines)
        all_headlines = [h for h in all_headlines
                         if any(p.search(h["title"]) for p in patterns)]
        logger.info("Keyword filter %s: %d -> %d headline(s)",
                    args.keyword, before, len(all_headlines))

    if not all_headlines:
        fail(logger, "No headlines collected from any source. "
                     "Check the URLs and scraper.log.")

    try:
        save(all_headlines, output, args.format, logger)
    except OSError as exc:
        fail(logger, f"Could not write {args.output}: {exc}")

    print("\n--- Scrape summary ---")
    print(f"Sources: {', '.join(sources)}")
    print(f"Headlines saved: {len(all_headlines)} -> {args.output} ({args.format})")
    if args.keyword:
        print(f"Keyword filter: {', '.join(args.keyword)}")
    if failed:
        print(f"Sources that failed: {', '.join(failed)}")
    print("Full log: scraper.log")
    for headline in all_headlines[:5]:
        print(f"  - {headline['title']}  ({headline['url']})")
    if len(all_headlines) > 5:
        print(f"  ... and {len(all_headlines) - 5} more in {args.output}")
    return 2 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
