"""Generate a custom GitHub stats SVG card from live API data."""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

USERNAME = "m4cd4r4"
DISPLAY_NAME = "Macdara \u00d3 Murch\u00fa"


def api(endpoint):
    """Call GitHub API with optional auth."""
    url = (
        endpoint
        if endpoint.startswith("https://")
        else f"https://api.github.com/{endpoint}"
    )
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"API error {e.code} for {url}")
        return None


def fetch_stats():
    """Gather all public stats from GitHub API."""
    user = api(f"users/{USERNAME}")
    year = datetime.now(timezone.utc).year

    pr_total = api(f"search/issues?q=author:{USERNAME}+type:pr")
    pr_merged = api(f"search/issues?q=author:{USERNAME}+type:pr+is:merged")
    pr_open = api(f"search/issues?q=author:{USERNAME}+type:pr+is:open")
    issues = api(f"search/issues?q=author:{USERNAME}+type:issue")
    commits = api(
        f"search/commits?q=author:{USERNAME}+committer-date:>{year}-01-01"
    )
    ext_merged = api(
        f"search/issues?q=author:{USERNAME}+type:pr+is:merged+-user:{USERNAME}&per_page=100"
    )
    reviews = api(
        f"search/issues?q=reviewed-by:{USERNAME}+type:pr+-author:{USERNAME}"
    )

    repos = api(f"users/{USERNAME}/repos?per_page=100&type=public")
    stars = sum(r.get("stargazers_count", 0) for r in (repos or []))
    forks = sum(r.get("forks_count", 0) for r in (repos or []))

    # Unique orgs contributed to
    ext_orgs = set()
    if ext_merged and ext_merged.get("items"):
        for item in ext_merged["items"]:
            repo_url = item.get("repository_url", "")
            org = repo_url.split("/")[-2] if "/" in repo_url else ""
            if org and org != USERNAME:
                ext_orgs.add(org)

    # Language breakdown from repos
    langs = {}
    for r in repos or []:
        lang = r.get("language")
        if lang:
            langs[lang] = langs.get(lang, 0) + 1
    top_langs = sorted(langs.items(), key=lambda x: -x[1])[:6]

    return {
        "public_repos": user.get("public_repos", 0) if user else 0,
        "followers": user.get("followers", 0) if user else 0,
        "stars": stars,
        "forks": forks,
        "pr_total": pr_total.get("total_count", 0) if pr_total else 0,
        "pr_merged": pr_merged.get("total_count", 0) if pr_merged else 0,
        "pr_open": pr_open.get("total_count", 0) if pr_open else 0,
        "issues": issues.get("total_count", 0) if issues else 0,
        "commits_year": commits.get("total_count", 0) if commits else 0,
        "year": year,
        "ext_merged": ext_merged.get("total_count", 0) if ext_merged else 0,
        "ext_orgs": len(ext_orgs),
        "reviews": reviews.get("total_count", 0) if reviews else 0,
        "top_langs": top_langs,
        "updated": datetime.now(timezone.utc).strftime("%b %d, %Y"),
    }


LANG_COLORS = {
    "TypeScript": "#3178C6",
    "Python": "#3572A5",
    "JavaScript": "#F1E05A",
    "HTML": "#E34C26",
    "CSS": "#563D7C",
    "Rust": "#DEA584",
    "Go": "#00ADD8",
    "Shell": "#89E051",
    "PowerShell": "#012456",
    "Jupyter Notebook": "#DA5B0B",
    "C++": "#F34B7D",
    "Java": "#B07219",
    "Ruby": "#701516",
    "Swift": "#F05138",
}


def lang_bar_svg(top_langs, y_start, width=460):
    """Generate a language distribution bar with legend."""
    total = sum(c for _, c in top_langs)
    if total == 0:
        return ""

    bar_y = y_start
    bar_h = 8
    legend_y = bar_y + 22
    radius = 4

    # Build clip path and colored segments
    segments = []
    x = 20
    usable = width - 40
    for i, (lang, count) in enumerate(top_langs):
        w = max(2, (count / total) * usable)
        color = LANG_COLORS.get(lang, "#8B8B8B")
        segments.append(
            f'<rect x="{x:.1f}" y="{bar_y}" width="{w:.1f}" '
            f'height="{bar_h}" fill="{color}"'
            + (f' rx="{radius}" ry="{radius}"' if i == 0 else "")
            + (
                f' rx="{radius}" ry="{radius}"'
                if i == len(top_langs) - 1
                else ""
            )
            + " />"
        )
        x += w

    bar_svg = "\n".join(segments)

    # Rounded bar with clipping
    bar_svg = f"""
    <defs>
      <clipPath id="lang-clip">
        <rect x="20" y="{bar_y}" width="{usable}" height="{bar_h}" rx="{radius}" ry="{radius}" />
      </clipPath>
    </defs>
    <g clip-path="url(#lang-clip)">
      {bar_svg}
    </g>"""

    # Legend dots
    legend_items = []
    lx = 20
    for lang, count in top_langs:
        pct = (count / total) * 100
        color = LANG_COLORS.get(lang, "#8B8B8B")
        legend_items.append(
            f'<circle cx="{lx + 4}" cy="{legend_y}" r="4" fill="{color}" />'
            f'<text x="{lx + 12}" y="{legend_y + 4}" '
            f'fill="#8B949E" font-size="11" font-family="Segoe UI, Ubuntu, sans-serif">'
            f"{lang} {pct:.1f}%</text>"
        )
        text_width = len(f"{lang} {pct:.1f}%") * 6.5 + 20
        lx += text_width
        if lx > width - 40:
            lx = 20
            legend_y += 18

    return bar_svg + "\n" + "\n".join(legend_items), legend_y + 14


def generate_svg(stats):
    """Build the complete SVG card."""
    w = 460
    accent = "#58A6FF"
    green = "#3FB950"
    yellow = "#D29922"
    purple = "#BC8CFF"
    text = "#C9D1D9"
    dim = "#8B949E"
    bg = "#0D1117"
    border = "#30363D"

    def fmt(n):
        if n >= 1000:
            return f"{n/1000:.1f}k"
        return str(n)

    def stat_row(icon, label, value, color, y):
        return f"""
    <g transform="translate(0, {y})">
      <text x="32" y="0" fill="{color}" font-size="14">{icon}</text>
      <text x="52" y="0" fill="{text}" font-size="13"
            font-family="Segoe UI, Ubuntu, sans-serif">{label}</text>
      <text x="{w - 28}" y="0" fill="{color}" font-size="13" text-anchor="end"
            font-family="Segoe UI, Ubuntu, sans-serif" font-weight="600">{value}</text>
    </g>"""

    # Build rows
    y = 56
    rows = ""

    rows += stat_row(
        "\u2b50", "Public Stars Earned", fmt(stats["stars"]), accent, y
    )
    y += 28
    rows += stat_row(
        "\U0001f4bb",
        f"Public Commits ({stats['year']})",
        fmt(stats["commits_year"]),
        accent,
        y,
    )
    y += 28
    rows += stat_row(
        "\U0001f501",
        f"Public PRs (merged / open / total)",
        f"{fmt(stats['pr_merged'])} / {stats['pr_open']} / {fmt(stats['pr_total'])}",
        green,
        y,
    )
    y += 28
    rows += stat_row(
        "\U0001f30d",
        f"OSS Contributions (merged across {stats['ext_orgs']} orgs)",
        str(stats["ext_merged"]),
        purple,
        y,
    )
    y += 28
    rows += stat_row(
        "\U0001f4e6", "Public Repos", str(stats["public_repos"]), accent, y
    )
    y += 28
    rows += stat_row(
        "\U0001f4ac", "Public Issues Opened", str(stats["issues"]), yellow, y
    )
    y += 28
    rows += stat_row(
        "\U0001f440", "PRs Reviewed", str(stats["reviews"]), dim, y
    )
    y += 28
    rows += stat_row(
        "\U0001f31f", "Followers", str(stats["followers"]), dim, y
    )

    # Language section
    y += 36
    lang_section = f"""
    <text x="20" y="{y}" fill="{text}" font-size="13"
          font-family="Segoe UI, Ubuntu, sans-serif" font-weight="600">
      Languages (by public repo count)
    </text>"""
    y += 16

    lang_bar, lang_end_y = lang_bar_svg(stats["top_langs"], y, w)
    lang_section += lang_bar

    # Footer
    footer_y = lang_end_y + 16
    footer = f"""
    <text x="{w / 2}" y="{footer_y}" fill="{dim}" font-size="10" text-anchor="middle"
          font-family="Segoe UI, Ubuntu, sans-serif">
      Updated {stats['updated']} - generated from live GitHub API data
    </text>"""

    h = footer_y + 20

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <rect width="{w}" height="{h}" rx="6" ry="6" fill="{bg}" stroke="{border}" stroke-width="1" />

  <text x="20" y="30" fill="{text}" font-size="16"
        font-family="Segoe UI, Ubuntu, sans-serif" font-weight="700">
    {DISPLAY_NAME}'s Public GitHub Stats
  </text>
  <line x1="20" y1="40" x2="{w - 20}" y2="40" stroke="{border}" stroke-width="1" />

  {rows}
  {lang_section}
  {footer}
</svg>"""

    return svg


if __name__ == "__main__":
    print("Fetching GitHub stats...")
    stats = fetch_stats()
    print(f"  Repos: {stats['public_repos']}, PRs: {stats['pr_total']}, "
          f"Commits ({stats['year']}): {stats['commits_year']}")

    svg = generate_svg(stats)
    out = os.path.join(os.path.dirname(__file__), "..", "assets", "stats.svg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Written to {os.path.abspath(out)}")
