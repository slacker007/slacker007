"""Generate contribution cards directly from GitHub, using only the stdlib."""

import json
import os
from datetime import date, datetime, timedelta, timezone
from html import escape
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree


def graphql(query, variables):
    request = Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"Bearer {os.environ['GITHUB_TOKEN']}",
            "Content-Type": "application/json",
            "User-Agent": "profile-contribution-cards",
        },
    )
    with urlopen(request, timeout=60) as response:
        result = json.load(response)
    if result.get("errors"):
        raise RuntimeError(f"GitHub GraphQL error: {result['errors']}")
    if not result.get("data", {}).get("user"):
        raise RuntimeError("GitHub returned no user data")
    return result["data"]["user"]


def fetch_days(username, today):
    user = graphql(
        "query($login: String!) { user(login: $login) { createdAt } }",
        {"login": username},
    )
    first_year = int(user["createdAt"][:4])
    days = {}
    for year in range(first_year, today.year + 1):
        start = date(year, 1, 1)
        end = min(date(year, 12, 31), today)
        user = graphql(
            """query($login: String!, $from: DateTime!, $to: DateTime!) {
              user(login: $login) {
                contributionsCollection(from: $from, to: $to) {
                  contributionCalendar {
                    weeks { contributionDays { date contributionCount } }
                  }
                }
              }
            }""",
            {
                "login": username,
                "from": f"{start}T00:00:00Z",
                "to": f"{end}T23:59:59Z",
            },
        )
        calendar = user["contributionsCollection"]["contributionCalendar"]
        for week in calendar["weeks"]:
            for day in week["contributionDays"]:
                day_date = date.fromisoformat(day["date"])
                if start <= day_date <= end:
                    days[day_date] = day["contributionCount"]
        # Never silently turn a partial API response into zero contributions.
        if any(start + timedelta(days=i) not in days for i in range((end - start).days + 1)):
            raise RuntimeError(f"Incomplete contribution calendar for {year}")
    return days


def streaks(days, today):
    """Count consecutive dates, allowing today to be unfinished (UTC)."""
    longest = run = 0
    previous = None
    for day, count in sorted(days.items()):
        if day > today:
            continue
        if count:
            run = run + 1 if previous == day - timedelta(days=1) else 1
        else:
            run = 0
        longest = max(longest, run)
        previous = day

    current = 0
    cursor = today if days.get(today, 0) else today - timedelta(days=1)
    while days.get(cursor, 0):
        current += 1
        cursor -= timedelta(days=1)
    return current, longest


def text(x, y, value, size=14, color="#a9fef7", anchor="start"):
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'text-anchor="{anchor}">{escape(str(value))}</text>'
    )


def card(title, description, body, width=495, height=195):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">'
        f'<title id="title">{escape(title)}</title><desc id="desc">{escape(description)}</desc>'
        f'<rect width="{width}" height="{height}" rx="5" fill="#141321"/>'
        '<g font-family="DejaVu Sans, Verdana, sans-serif">'
        + body + '</g></svg>\n'
    )


def streak_card(days, today):
    current, longest = streaks(days, today)
    total = sum(count for day, count in days.items() if day <= today)
    title = "GitHub Contribution Streak"
    body = text(25, 32, title, 18, "#fe428e")
    for x, value, label in (
        (85, total, "Contributions"),
        (247, current, "Current streak"),
        (410, longest, "Longest streak"),
    ):
        body += text(x, 91, f"{value:,}", 30, "#f8d847", "middle")
        body += text(x, 120, label, 12, anchor="middle")
    body += text(247, 150, f"Since {min(days).year} · streaks in days", 11, anchor="middle")
    body += text(247, 175, f"Updated {today.isoformat()} UTC", 10, "#a0a0b0", "middle")
    return card(title, f"{total} contributions, {current} day current streak, {longest} day longest streak.", body)


def activity_card(days, today):
    start = today - timedelta(days=30)
    recent = [(start + timedelta(days=i), days.get(start + timedelta(days=i), 0)) for i in range(31)]
    maximum = max(1, max(count for _, count in recent))
    left, right, top, bottom = 55, 945, 65, 240
    title = "Contribution Activity · Last 31 Days"
    body = text(25, 32, title, 18, "#fe428e")
    for fraction in (0, 0.5, 1):
        y = bottom - fraction * (bottom - top)
        body += f'<path d="M {left} {y} H {right}" stroke="#2d2b40"/>'
        body += text(44, y + 4, f"{maximum * fraction:g}", 11, anchor="end")
    points = []
    for index, (day, count) in enumerate(recent):
        x = left + index * (right - left) / 30
        y = bottom - count / maximum * (bottom - top)
        points.append(f"{x:.1f},{y:.1f}")
        if index % 5 == 0:
            body += text(x, 264, day.strftime("%b %d"), 11, anchor="middle")
    coordinates = " ".join(points)
    body += f'<polygon points="{left},{bottom} {coordinates} {right},{bottom}" fill="#fe428e" opacity="0.12"/>'
    body += f'<polyline points="{coordinates}" fill="none" stroke="#fe428e" stroke-width="3" stroke-linejoin="round"/>'
    for point, (day, count) in zip(points, recent):
        x, y = point.split(",")
        body += f'<circle cx="{x}" cy="{y}" r="3" fill="#f8d847"><title>{day}: {count} contributions</title></circle>'
    body += text(945, 288, f"Updated {today.isoformat()} UTC", 10, "#a0a0b0", "end")
    description = "; ".join(f"{day}: {count}" for day, count in recent)
    return card(title, description, body, width=990, height=305)


def main():
    today = datetime.now(timezone.utc).date()
    username = os.environ.get("PROFILE_USERNAME", "slacker007")
    days = fetch_days(username, today)
    cards = {"streak.svg": streak_card(days, today), "activity.svg": activity_card(days, today)}
    output = Path("profile")
    output.mkdir(exist_ok=True)
    for name, svg in cards.items():
        ElementTree.fromstring(svg)
        (output / name).write_text(svg, encoding="utf-8")
        print(f"Generated {output / name}")


if __name__ == "__main__":
    main()
