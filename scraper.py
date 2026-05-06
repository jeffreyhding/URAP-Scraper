"""
scraper.py — Scrape a URAP project description and save it as a Markdown file.

Usage:
    python scraper.py <url>
    python scraper.py <id>
    python scraper.py <id1> <id2> <id3> ...

Examples:
    python scraper.py https://urapprojects.berkeley.edu/detail.php?id=20176-1
    python scraper.py 20176-1
    python scraper.py 20176-1 20402-3 20402-4 20425-1
"""

import re
import sys
import textwrap
from pathlib import Path
from urllib.parse import urlparse, parse_qs
 
import requests
from bs4 import BeautifulSoup, NavigableString, Tag
 
BASE_URL = "https://urapprojects.berkeley.edu/detail.php?id="
 
 
# URL / ID helpers 
def parse_input(arg: str) -> tuple[str, str]:
    """Return (full_url, project_id) from either a URL or a bare ID string."""
    arg = arg.strip()
    if arg.startswith("http"):
        parsed = urlparse(arg)
        qs = parse_qs(parsed.query)
        project_id = qs.get("id", [None])[0]
        if not project_id:
            raise ValueError(f"Could not extract 'id' from URL: {arg}")
        return arg, project_id
    # assume bare ID like "20176-1"
    if re.fullmatch(r"\d+-\d+", arg):
        return BASE_URL + arg, arg
    raise ValueError(
        f"Argument '{arg}' is neither a valid URAP URL nor a bare project ID "
        "(expected format: 20176-1)."
    )
 
 
# Fetch 
def fetch_page(url: str) -> BeautifulSoup:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        )
    }
    resp = requests.get(url, headers=headers, timeout=15)
    resp.raise_for_status()
    return BeautifulSoup(resp.text, "html.parser")
 
 
# HTML to Markdown conversion 
def element_to_md(el: Tag | NavigableString) -> str:
    """Recursively convert a BS4 element tree to Markdown text."""
    if isinstance(el, NavigableString):
        return str(el)
 
    tag = el.name.lower() if el.name else ""
 
    # collect children text
    inner = "".join(element_to_md(c) for c in el.children)
 
    if tag in ("b", "strong"):
        stripped = inner.strip()
        return f"**{stripped}**" if stripped else ""
 
    if tag in ("i", "em"):
        stripped = inner.strip()
        return f"*{stripped}*" if stripped else ""
 
    if tag == "a":
        href = el.get("href", "").strip()
        text = inner.strip()
 
        # Internal URAP navigation links — two cases:
        # 1. Faculty / department labels (list.php?faculty_*): keep text, drop link
        # 2. Category tags and "Return to Project List" (list.php*): drop entirely
        if "list.php" in href:
            if "faculty_id" in href or "faculty_department" in href:
                return text  # plain text, no markdown link
            return ""        # discard category tags and nav links entirely
 
        if href and text:
            return f"[{text}]({href})"
        return text or href
 
    if tag in ("br",):
        return "  \n"
 
    if tag in ("p", "div", "section"):
        text = inner.strip()
        return f"\n\n{text}\n\n" if text else ""
 
    if tag in ("h1", "h2", "h3", "h4"):
        level = int(tag[1])
        text = inner.strip()
        return f"\n\n{'#' * level} {text}\n\n" if text else ""
 
    if tag in ("ul", "ol"):
        items = []
        for i, li in enumerate(el.find_all("li", recursive=False), 1):
            li_text = element_to_md(li).strip()
            prefix = f"{i}." if tag == "ol" else "-"
            items.append(f"{prefix} {li_text}")
        return "\n" + "\n".join(items) + "\n"
 
    if tag == "li":
        return inner.strip()
 
    if tag in ("script", "style", "head", "nav", "footer", "header", "form"):
        return ""
 
    return inner
 
 
## Find the main content block
# Candidate selectors tried in order, first match wins
CONTENT_SELECTORS = [
    {"id": "content"},
    {"id": "main-content"},
    {"id": "project-detail"},
    {"class": "project-detail"},
    {"class": "project_detail"},
    {"id": "project_detail"},
    {"class": "content"},
    {"class": "main-content"},
    {"id": "main"},
    {"role": "main"},
]
 
def find_content(soup: BeautifulSoup) -> Tag:
    for attrs in CONTENT_SELECTORS:
        el = soup.find(True, attrs)
        if el:
            return el
    # Fallback: body minus obvious chrome
    body = soup.find("body")
    if body:
        for tag in body.find_all(["nav", "header", "footer", "script", "style"]):
            tag.decompose()
        return body
    return soup
 
 
## Post-process raw markdown text
 
def clean_markdown(text: str, url: str) -> str:
    # Collapse 3+ blank lines to 2
    text = re.sub(r"\n{3,}", "\n\n", text)
 
    # Ensure bold labels like "Role:" "Qualifications:" etc. are on their own line
    # (some pages render them inline)
    text = re.sub(
        r"(?<!\n)\n?(\*\*(?:Role|Qualifications?|Required|Desirable|Hours"
        r"|Day-to-day supervisor[^*]*|Off-Campus[^*]*|Related website"
        r"|Learning [Oo]utcomes?|Tasks?)[^*]*\*\*)",
        r"\n\n\1",
        text,
    )
 
    # Prepend the URL as a markdown link at the very top
    url_line = f"[{url}]({url})"
    text = url_line + "\n\n" + text.lstrip()
 
    return text.rstrip() + "\n"
 
 
# Main scrape-and-save function
def scrape(url: str, project_id: str, output_dir: Path = Path(".")) -> Path:
    print(f"  Fetching  {url}")
    soup = fetch_page(url)
 
    content_el = find_content(soup)
    raw_md = element_to_md(content_el)
    md = clean_markdown(raw_md, url)
 
    out_path = output_dir / f"{project_id}.md"
    out_path.write_text(md, encoding="utf-8")
    print(f"  Saved  @  {out_path}")
    return out_path
 
 
# CLI entry point
def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
 
    # Default: outputs/ folder next to this script
    output_dir = Path(__file__).parent / "outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    errors = []
 
    for arg in sys.argv[1:]:
        # allow --output=some/dir or -o some/dir
        if arg.startswith("--output="):
            output_dir = Path(arg.split("=", 1)[1])
            output_dir.mkdir(parents=True, exist_ok=True)
            continue
        if arg in ("-o", "--output"):
            # handled as next arg; skip here (set in next iteration via peek)
            continue
 
        try:
            url, project_id = parse_input(arg)
            scrape(url, project_id, output_dir)
        except requests.HTTPError as e:
            msg = f"HTTP error for '{arg}': {e}"
            print(f"  ERROR: {msg}", file=sys.stderr)
            errors.append(msg)
        except Exception as e:
            msg = f"Failed for '{arg}': {e}"
            print(f"  ERROR: {msg}", file=sys.stderr)
            errors.append(msg)
 
    if errors:
        sys.exit(1)
 
 
if __name__ == "__main__":
    main()