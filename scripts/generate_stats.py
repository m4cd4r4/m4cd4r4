"""Generate a custom GitHub stats SVG card from live API data.

Uses GraphQL for contribution data (includes private when PAT provided)
and REST for public-only counts. Shows public stats per-type with a
private contribution aggregate and clean repo/language splits.
"""

import json
import os
import urllib.request
import urllib.error
from datetime import datetime, timezone

USERNAME = "m4cd4r4"
DISPLAY_NAME = "Macdara \u00d3 Murch\u00fa"


def get_token():
    return os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")


def api(endpoint):
    """Call GitHub REST API."""
    url = (
        endpoint
        if endpoint.startswith("https://")
        else f"https://api.github.com/{endpoint}"
    )
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    token = get_token()
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"API error {e.code} for {url}")
        return None


def graphql(query, variables=None):
    """Call GitHub GraphQL API."""
    token = get_token()
    if not token:
        return None
    payload = json.dumps({"query": query, "variables": variables or {}}).encode()
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=payload,
        method="POST",
    )
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req) as resp:
            result = json.loads(resp.read())
            return result.get("data")
    except urllib.error.HTTPError as e:
        print(f"GraphQL error {e.code}")
        return None


def fetch_stats():
    """Gather public and total stats from GitHub API."""
    user = api(f"users/{USERNAME}")
    year = datetime.now(timezone.utc).year

    # --- GraphQL: contribution totals + repo counts + languages ---
    gql = graphql("""
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
          totalCommitContributions
          restrictedContributionsCount
          totalPullRequestContributions
          totalPullRequestReviewContributions
          totalIssueContributions
        }
        repositories(ownerAffiliations: [OWNER]) { totalCount }
        publicRepos: repositories(ownerAffiliations: [OWNER], privacy: PUBLIC) { totalCount }
        privateRepos: repositories(ownerAffiliations: [OWNER], privacy: PRIVATE) { totalCount }
        allRepoLangs: repositories(
          ownerAffiliations: [OWNER]
          first: 100
          orderBy: {field: PUSHED_AT, direction: DESC}
        ) {
          nodes { primaryLanguage { name } }
        }
      }
    }
    """, {
        "login": USERNAME,
        "from": f"{year}-01-01T00:00:00Z",
        "to": f"{year}-12-31T23:59:59Z",
    })

    has_private = False
    restricted_count = 0
    graph_commits = 0
    graph_prs = 0
    graph_issues = 0
    graph_reviews = 0
    total_repos = 0
    private_repos = 0
    all_langs = {}

    if gql and gql.get("user"):
        cc = gql["user"]["contributionsCollection"]
        graph_commits = cc["totalCommitContributions"]
        restricted_count = cc["restrictedContributionsCount"]
        has_private = restricted_count > 0
        graph_prs = cc["totalPullRequestContributions"]
        graph_issues = cc["totalIssueContributions"]
        graph_reviews = cc["totalPullRequestReviewContributions"]
        total_repos = gql["user"]["repositories"]["totalCount"]
        private_repos = gql["user"]["privateRepos"]["totalCount"]

        for node in gql["user"]["allRepoLangs"]["nodes"]:
            lang = node.get("primaryLanguage")
            if lang and lang.get("name"):
                all_langs[lang["name"]] = all_langs.get(lang["name"], 0) + 1

    # --- REST: public-only counts (all-time) ---
    pr_pub = api(f"search/issues?q=author:{USERNAME}+type:pr")
    pr_pub_merged = api(f"search/issues?q=author:{USERNAME}+type:pr+is:merged")
    pr_pub_open = api(f"search/issues?q=author:{USERNAME}+type:pr+is:open")
    issues_pub = api(f"search/issues?q=author:{USERNAME}+type:issue")
    ext_merged = api(
        f"search/issues?q=author:{USERNAME}+type:pr+is:merged+-user:{USERNAME}&per_page=100"
    )
    reviews_pub = api(
        f"search/issues?q=reviewed-by:{USERNAME}+type:pr+-author:{USERNAME}"
    )

    repos_pub = api(f"users/{USERNAME}/repos?per_page=100&type=public")
    stars = sum(r.get("stargazers_count", 0) for r in (repos_pub or []))

    # Unique orgs contributed to (external merged PRs)
    ext_orgs = set()
    if ext_merged and ext_merged.get("items"):
        for item in ext_merged["items"]:
            repo_url = item.get("repository_url", "")
            org = repo_url.split("/")[-2] if "/" in repo_url else ""
            if org and org != USERNAME:
                ext_orgs.add(org)

    # Public-only language breakdown (fallback)
    pub_langs = {}
    for r in repos_pub or []:
        lang = r.get("language")
        if lang:
            pub_langs[lang] = pub_langs.get(lang, 0) + 1

    lang_source = all_langs if all_langs else pub_langs
    top_langs = sorted(lang_source.items(), key=lambda x: -x[1])[:8]

    pub_repos = user.get("public_repos", 0) if user else 0

    return {
        "has_private": has_private,
        # Contribution graph (year-scoped)
        "graph_commits": graph_commits,
        "graph_prs": graph_prs,
        "graph_issues": graph_issues,
        "graph_reviews": graph_reviews,
        "restricted_count": restricted_count,
        "year": year,
        # Public all-time (REST search)
        "pub_prs": pr_pub.get("total_count", 0) if pr_pub else 0,
        "pub_prs_merged": pr_pub_merged.get("total_count", 0) if pr_pub_merged else 0,
        "pub_prs_open": pr_pub_open.get("total_count", 0) if pr_pub_open else 0,
        "pub_issues": issues_pub.get("total_count", 0) if issues_pub else 0,
        "pub_reviews": reviews_pub.get("total_count", 0) if reviews_pub else 0,
        # Repos
        "pub_repos": pub_repos,
        "total_repos": total_repos if has_private else pub_repos,
        "private_repos": private_repos,
        # Other
        "followers": user.get("followers", 0) if user else 0,
        "stars": stars,
        "ext_merged": ext_merged.get("total_count", 0) if ext_merged else 0,
        "ext_orgs": len(ext_orgs),
        "top_langs": top_langs,
        "langs_include_private": bool(all_langs),
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
    "C#": "#178600",
    "Dockerfile": "#384D54",
    "SCSS": "#C6538C",
    "MDX": "#FCB32C",
}


def lang_bar_svg(top_langs, y_start, width=490):
    """Generate a language distribution bar with legend."""
    total = sum(c for _, c in top_langs)
    if total == 0:
        return "", y_start

    bar_y = y_start
    bar_h = 8
    legend_y = bar_y + 22
    radius = 4

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
    bar_svg = f"""
    <defs>
      <clipPath id="lang-clip">
        <rect x="20" y="{bar_y}" width="{usable}" height="{bar_h}" rx="{radius}" ry="{radius}" />
      </clipPath>
    </defs>
    <g clip-path="url(#lang-clip)">
      {bar_svg}
    </g>"""

    legend_items = []
    lx = 20
    for lang, count in top_langs:
        pct = (count / total) * 100
        color = LANG_COLORS.get(lang, "#8B8B8B")
        legend_items.append(
            f'<circle cx="{lx + 4}" cy="{legend_y}" r="4" fill="{color}" />'
            f'<text x="{lx + 12}" y="{legend_y + 4}" '
            f'fill="#8B949E" font-size="11" font-family="Segoe UI, Ubuntu, sans-serif">'
            f"{lang} {pct:.0f}%</text>"
        )
        text_width = len(f"{lang} {pct:.0f}%") * 6.2 + 20
        lx += text_width
        if lx > width - 60:
            lx = 20
            legend_y += 18

    return bar_svg + "\n" + "\n".join(legend_items), legend_y + 14


def generate_svg(stats):
    """Build the complete SVG card."""
    w = 490
    accent = "#58A6FF"
    green = "#3FB950"
    yellow = "#D29922"
    purple = "#BC8CFF"
    text_color = "#C9D1D9"
    dim = "#8B949E"
    bg = "#0D1117"
    border = "#30363D"
    has_priv = stats["has_private"]

    def fmt(n):
        if n >= 1000:
            return f"{n / 1000:.1f}k"
        return str(n)

    def row(icon, label, value, color, y):
        return f"""
    <g transform="translate(0, {y})">
      <text x="32" y="0" fill="{color}" font-size="14">{icon}</text>
      <text x="52" y="0" fill="{text_color}" font-size="13"
            font-family="Segoe UI, Ubuntu, sans-serif">{label}</text>
      <text x="{w - 28}" y="0" fill="{color}" font-size="13" text-anchor="end"
            font-family="Segoe UI, Ubuntu, sans-serif" font-weight="600">{value}</text>
    </g>"""

    def split_row(icon, label, pub_val, total_val, color, y):
        """Row showing public / total."""
        return f"""
    <g transform="translate(0, {y})">
      <text x="32" y="0" fill="{color}" font-size="14">{icon}</text>
      <text x="52" y="0" fill="{text_color}" font-size="13"
            font-family="Segoe UI, Ubuntu, sans-serif">{label}</text>
      <text x="{w - 28}" y="0" fill="{dim}" font-size="13" text-anchor="end"
            font-family="Segoe UI, Ubuntu, sans-serif">
        <tspan fill="{color}" font-weight="600">{pub_val}</tspan>
        <tspan fill="{border}">  |  </tspan>
        <tspan fill="{color}" font-weight="600" opacity="0.5">{total_val}</tspan>
      </text>
    </g>"""

    def sub_text(text, y):
        return f"""
    <text x="52" y="{y}" fill="{dim}" font-size="11"
          font-family="Segoe UI, Ubuntu, sans-serif">{text}</text>"""

    title = f"{DISPLAY_NAME}'s GitHub Stats"

    y = 50
    header = ""
    if has_priv:
        header = f"""
    <text x="{w - 28}" y="{y}" fill="{dim}" font-size="10" text-anchor="end"
          font-family="Segoe UI, Ubuntu, sans-serif" letter-spacing="0.5">
      public  |  total
    </text>"""
        y += 18
    else:
        y += 6

    rows = ""

    # --- Contribution graph stats (year-scoped) ---
    rows += row(
        "\u2b50", "Stars Earned",
        fmt(stats["stars"]),
        accent, y,
    )
    y += 28

    rows += row(
        "\U0001f4bb", f"Commits ({stats['year']})",
        fmt(stats["graph_commits"]),
        accent, y,
    )
    y += 28

    # PRs - public all-time from REST
    rows += row(
        "\U0001f501", "Pull Requests",
        fmt(stats["pub_prs"]),
        green, y,
    )
    y += 20
    rows += sub_text(
        f"{fmt(stats['pub_prs_merged'])} merged / {stats['pub_prs_open']} open (public, all time)",
        y,
    )
    y += 24

    # OSS contributions
    rows += row(
        "\U0001f30d",
        f"OSS Contributions ({stats['ext_orgs']} orgs)",
        str(stats["ext_merged"]),
        purple, y,
    )
    y += 28

    # Repos - clean split
    if has_priv:
        rows += split_row(
            "\U0001f4e6", "Repos",
            str(stats["pub_repos"]), str(stats["total_repos"]),
            accent, y,
        )
    else:
        rows += row(
            "\U0001f4e6", "Public Repos",
            str(stats["pub_repos"]),
            accent, y,
        )
    y += 28

    # Issues
    rows += row(
        "\U0001f4ac", "Issues Opened",
        str(stats["pub_issues"]),
        yellow, y,
    )
    y += 28

    # Reviews
    rows += row(
        "\U0001f440", "PRs Reviewed",
        str(stats["pub_reviews"]),
        dim, y,
    )
    y += 28

    # Followers
    rows += row(
        "\U0001f31f", "Followers",
        str(stats["followers"]),
        dim, y,
    )

    # --- Private contributions callout ---
    if has_priv and stats["restricted_count"] > 0:
        y += 32
        rc = stats["restricted_count"]
        rows += f"""
    <rect x="20" y="{y - 14}" width="{w - 40}" height="24" rx="4" ry="4"
          fill="#161B22" stroke="{border}" stroke-width="1" />
    <text x="{w / 2}" y="{y + 2}" fill="{dim}" font-size="11" text-anchor="middle"
          font-family="Segoe UI, Ubuntu, sans-serif">
      <tspan fill="{purple}" font-weight="600">+{fmt(rc)}</tspan>
      <tspan> private contributions in {stats['year']}</tspan>
    </text>"""

    # --- Language section ---
    y += 36
    lang_label = "Languages (all repos)" if stats["langs_include_private"] else "Languages (public repos)"
    lang_section = f"""
    <text x="20" y="{y}" fill="{text_color}" font-size="13"
          font-family="Segoe UI, Ubuntu, sans-serif" font-weight="600">
      {lang_label}
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

  <text x="20" y="30" fill="{text_color}" font-size="16"
        font-family="Segoe UI, Ubuntu, sans-serif" font-weight="700">
    {title}
  </text>
  <line x1="20" y1="40" x2="{w - 20}" y2="40" stroke="{border}" stroke-width="1" />

  {header}
  {rows}
  {lang_section}
  {footer}
</svg>"""

    return svg


if __name__ == "__main__":
    print("Fetching GitHub stats...")
    stats = fetch_stats()
    priv_label = " (includes private)" if stats["has_private"] else " (public only)"
    print(f"  Repos: {stats['pub_repos']} public / {stats['total_repos']} total ({stats['private_repos']} private)")
    print(f"  Commits ({stats['year']}, graph): {stats['graph_commits']}")
    print(f"  PRs (public, all-time): {stats['pub_prs']}")
    print(f"  Restricted contributions ({stats['year']}): {stats['restricted_count']}")
    print(f"  Languages: {len(stats['top_langs'])} ({priv_label})")

    svg = generate_svg(stats)
    out = os.path.join(os.path.dirname(__file__), "..", "assets", "stats.svg")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write(svg)
    print(f"Written to {os.path.abspath(out)}")
