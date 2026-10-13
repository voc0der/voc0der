"""Refresh the profile's upstream PR panel using public GitHub data."""

import json
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from html import escape
from pathlib import Path

USER = "voc0der"
ROOT = Path(__file__).resolve().parents[1]
QUERY = f"is:pr author:{USER} -user:{USER} is:public"


def fetch_pull_requests():
    """Paginate public search without exposing private account activity."""
    items = {}
    for page in range(1, 11):
        params = urllib.parse.urlencode({
            "q": QUERY, "per_page": 100, "page": page,
            "sort": "created", "order": "asc",
        })
        request = urllib.request.Request(
            f"https://api.github.com/search/issues?{params}",
            headers={"Accept": "application/vnd.github+json",
                     "User-Agent": f"{USER}-profile"},
        )
        # Public search deliberately uses no account token.
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        if data["incomplete_results"] or data["total_count"] > 1000:
            raise RuntimeError("Incomplete search; keeping the existing panel.")
        for item in data["items"]:
            items[item["id"]] = item
        if len(items) >= data["total_count"]:
            return list(items.values())
        if not data["items"]:
            break
    raise RuntimeError("Missing search results; keeping the existing panel.")


def summarize(items):
    projects = defaultdict(lambda: {"merged": 0, "open": 0})
    seen = set()
    for item in items:
        if item["id"] in seen:
            continue
        seen.add(item["id"])
        repo = "/".join(item["repository_url"].split("/")[-2:])
        if repo.split("/")[0].casefold() == USER.casefold():
            continue
        pr = item.get("pull_request")
        if not pr:
            continue
        if pr.get("merged_at"):
            projects[repo]["merged"] += 1
        elif item["state"] == "open":
            projects[repo]["open"] += 1
    return sorted(projects.items(), key=lambda row: (
        -row[1]["merged"], -row[1]["open"], row[0].casefold(),
    ))


def render(projects, updated, dark=False):
    colors = (
        {"bg": "#0d1117", "fg": "#e6edf3", "muted": "#9198a1",
         "line": "#30363d", "link": "#58a6ff", "merged": "#bc8cff",
         "open": "#3fb950", "track": "#21262d"}
        if dark else
        {"bg": "#ffffff", "fg": "#1f2328", "muted": "#656d76",
         "line": "#d8dee4", "link": "#0969da", "merged": "#8250df",
         "open": "#1a7f37", "track": "#eaeef2"}
    )
    merged = sum(counts["merged"] for _, counts in projects)
    opened = sum(counts["open"] for _, counts in projects)
    count = sum(counts["merged"] > 0 for _, counts in projects)
    height = 155 + 34 * len(projects)
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="680" '
        f'height="{height}" viewBox="0 0 680 {height}" role="img" '
        'aria-labelledby="title description">',
        '<title id="title">Upstream contributions</title>',
        f'<desc id="description">{merged} merged pull requests across '
        f'{count} projects and {opened} open pull requests. '
        'Only public pull requests to repositories owned by others are included. '
        'Closed, unmerged proposals are omitted.</desc>',
        '<style>text{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Helvetica,Arial,sans-serif;'
        'font-size:14px} .small{font-size:12px} .number{font-variant-numeric:tabular-nums}</style>',
        f'<rect width="680" height="{height}" rx="8" fill="{colors["bg"]}"/>',
    ]

    def text(x, y, label, fill="fg", extra=""):
        parts.append(f'<text x="{x}" y="{y}" fill="{colors[fill]}" '
                     f'{extra}>{escape(str(label))}</text>')

    # A small branch icon keeps the panel close to GitHub's visual language.
    parts.append(f'<g fill="none" stroke="{colors["muted"]}" '
                 'stroke-width="1.5" transform="translate(15 15)">'
                 '<circle cx="4" cy="3" r="2.5"/>'
                 '<circle cx="4" cy="17" r="2.5"/>'
                 '<circle cx="16" cy="3" r="2.5"/>'
                 '<path d="M4 5.5v9M16 5.5v2.5c0 4-12 2-12 6"/></g>')
    text(44, 32, "Upstream contributions", "link", 'style="font-size:19px;font-weight:600"')
    text(16, 60, f"{merged} merged pull requests across {count} projects", "muted")
    text(650, 60, f"{opened} open", "open", 'text-anchor="end"')
    text(16, 99, "PROJECT", "muted", 'class="small"')
    text(574, 99, "MERGED", "muted", 'class="small" text-anchor="end"')
    text(650, 99, "OPEN", "muted", 'class="small" text-anchor="end"')
    parts.append(f'<path d="M16 111H650" stroke="{colors["line"]}"/>')
    maximum = max((c["merged"] + c["open"] for _, c in projects), default=1)
    for index, (repo, counts) in enumerate(projects):
        y = 137 + index * 34
        # Keep long names within their column; the full name stays in the title.
        label = repo if len(repo) <= 44 else repo[:41] + "…"
        parts.append(f'<g><title>{escape(repo)}</title>')
        text(16, y, label, "link", 'style="font-size:13px"')
        parts.append(f'<rect x="412" y="{y-8}" width="80" height="5" '
                     f'rx="2.5" fill="{colors["track"]}"/>')
        start = 412
        for state in ["merged", "open"]:
            width = 80 * counts[state] / maximum
            if width:
                parts.append(f'<rect x="{start:.2f}" y="{y-8}" '
                             f'width="{width:.2f}" height="5" '
                             f'fill="{colors[state]}"/>')
                start += width
        for x, state in [(574, "merged"), (650, "open")]:
            text(x, y, counts[state] or "—", state if counts[state] else "muted",
                 'class="number" text-anchor="end"')
        parts.append('</g>')
    text(16, height-12, "Merged and open PRs · all time", "muted", 'class="small"')
    text(650, height-12, f"Updated {updated}", "muted", 'class="small" text-anchor="end"')
    parts.append('</svg>')
    return "\n".join(parts) + "\n"


def main():
    projects = summarize(fetch_pull_requests())
    updated = datetime.now(timezone.utc).date().isoformat()
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    for theme in ["light", "dark"]:
        (assets / f"contributions-{theme}.svg").write_text(
            render(projects, updated, dark=theme == "dark"), encoding="utf-8",
        )
    print(f"Updated contribution panels for {len(projects)} upstream projects.")


if __name__ == "__main__":
    main()
