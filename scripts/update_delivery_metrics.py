from __future__ import annotations

import datetime as dt
import json
import os
import re
import statistics
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

REPO = os.environ["GITHUB_REPOSITORY"]
TOKEN = os.environ["GITHUB_TOKEN"]
API = "https://api.github.com"
ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "docs/product/delivery-metrics-config.json"
OUTPUT_PATH = ROOT / "docs/product/delivery-metrics.md"

SPRINT_RE = re.compile(r"\[(Sprint [^\]]+)\]")
ESTIMATE_RE = re.compile(r"\*\*Estimate:\*\*\s*(\d+)\s*SP", re.IGNORECASE)


def api_get(path: str, params: dict[str, str] | None = None) -> Any:
    url = f"{API}{path}"
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "tropos-delivery-metrics",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def paginate(path: str, params: dict[str, str] | None = None) -> list[dict[str, Any]]:
    params = dict(params or {})
    params["per_page"] = "100"
    rows: list[dict[str, Any]] = []
    page = 1
    while True:
        params["page"] = str(page)
        batch = api_get(path, params)
        if not batch:
            return rows
        rows.extend(batch)
        if len(batch) < 100:
            return rows
        page += 1


def parse_story(issue: dict[str, Any]) -> dict[str, Any] | None:
    if "pull_request" in issue:
        return None
    sprint_match = SPRINT_RE.search(issue.get("title", ""))
    estimate_match = ESTIMATE_RE.search(issue.get("body") or "")
    if not sprint_match or not estimate_match:
        return None
    return {
        "number": issue["number"],
        "sprint": sprint_match.group(1),
        "sp": int(estimate_match.group(1)),
        "state": issue["state"],
        "created_at": issue["created_at"],
        "closed_at": issue.get("closed_at"),
    }


def iso(value: str) -> dt.datetime:
    return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))


def median_hours(values: list[float]) -> str:
    return "N/A" if not values else f"{statistics.median(values):.1f} h"


def sprint_metrics(stories: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for story in stories:
        item = result.setdefault(story["sprint"], {"planned": 0, "completed": 0, "remaining": 0})
        item["planned"] += story["sp"]
        if story["state"] == "closed":
            item["completed"] += story["sp"]
        else:
            item["remaining"] += story["sp"]
    return result


def burndown(stories: list[dict[str, Any]], start: str | None, end: str | None) -> str:
    if not start or not end:
        return "_Actual burndown will render automatically after sprint start/end dates are configured._"

    start_date = dt.date.fromisoformat(start)
    end_date = dt.date.fromisoformat(end)
    planned = sum(s["sp"] for s in stories)

    days: list[dt.date] = []
    cursor = start_date
    while cursor <= end_date:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += dt.timedelta(days=1)

    remaining: list[int] = []
    for day in days:
        completed = sum(
            s["sp"] for s in stories
            if s["closed_at"] and iso(s["closed_at"]).date() <= day
        )
        remaining.append(max(planned - completed, 0))

    labels = ",".join(f'"{d.strftime("%d %b")}"' for d in days)
    values = ",".join(str(v) for v in remaining)
    ideal = ",".join(
        str(round(planned * (1 - i / max(len(days) - 1, 1))))
        for i in range(len(days))
    )
    fence = chr(96) * 3
    y_max = max([planned, *remaining, 1])
    return "\n".join([
        fence + "mermaid",
        "xychart-beta",
        '    title "Current Sprint Burndown"',
        f"    x-axis [{labels}]",
        f'    y-axis "Remaining Story Points" 0 --> {y_max}',
        f"    line [{ideal}]",
        f"    line [{values}]",
        fence,
    ])


def main() -> None:
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    issues = paginate(f"/repos/{REPO}/issues", {"state": "all"})
    stories = [story for issue in issues if (story := parse_story(issue)) is not None]
    metrics = sprint_metrics(stories)

    prs = paginate(f"/repos/{REPO}/pulls", {"state": "closed"})
    pr_cycle = [
        (iso(pr["merged_at"]) - iso(pr["created_at"])).total_seconds() / 3600
        for pr in prs if pr.get("merged_at")
    ]

    deployments = paginate(f"/repos/{REPO}/deployments")
    prod_names = {name.lower() for name in config.get("production_environment_names", [])}
    prod_deployments = [
        dep for dep in deployments
        if (dep.get("environment") or "").lower() in prod_names
    ]
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=30)
    recent_prod = [dep for dep in prod_deployments if iso(dep["created_at"]) >= cutoff]

    lead_times: list[float] = []
    for dep in recent_prod:
        sha = dep.get("sha")
        if not sha:
            continue
        try:
            commit = api_get(f"/repos/{REPO}/commits/{sha}")
            committed_at = commit["commit"]["committer"]["date"]
            lead_times.append((iso(dep["created_at"]) - iso(committed_at)).total_seconds() / 3600)
        except Exception:
            continue

    current = config["current_sprint"]
    current_stories = [s for s in stories if s["sprint"] == current]
    current_cfg = config.get("sprints", {}).get(current, {})

    sprint_order = sorted(metrics)
    labels = ",".join(f'"{s}"' for s in sprint_order) or '"No sprint"'
    values = ",".join(str(metrics[s]["completed"]) for s in sprint_order) or "0"
    velocity_max = max([metrics[s]["completed"] for s in sprint_order] + [1])
    rows = "\n".join(
        f"| {sprint} | {m['planned']} | {m['completed']} | {m['remaining']} |"
        for sprint, m in sorted(metrics.items())
    ) or "| No sprint stories found | 0 | 0 | 0 |"

    fence = chr(96) * 3
    generated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    text = f"""# Tropos Delivery & DORA Metrics

> Generated automatically from GitHub repository data. Do not edit manually.
> Last generated: {generated}

## Sprint delivery

| Sprint | Planned SP | Completed SP | Remaining SP |
|---|---:|---:|---:|
{rows}

### Current sprint burndown — {current}

{burndown(current_stories, current_cfg.get("start"), current_cfg.get("end"))}

### Velocity

Velocity is accepted story points completed in each sprint. It is a team forecasting metric, not an individual productivity metric.

{fence}mermaid
xychart-beta
    title "Completed Story Points by Sprint"
    x-axis [{labels}]
    y-axis "Completed Story Points" 0 --> {velocity_max}
    bar [{values}]
{fence}

## Engineering flow

| Metric | Current value | Definition |
|---|---:|---|
| Median PR cycle time | {median_hours(pr_cycle)} | PR opened to merged |
| Open current-sprint stories | {sum(1 for s in current_stories if s["state"] == "open")} | Current-sprint issues not yet closed |
| Current-sprint remaining work | {sum(s["sp"] for s in current_stories if s["state"] == "open")} SP | Unaccepted story points |

## DORA metrics

| DORA metric | Current value | Measurement source |
|---|---:|---|
| Deployment frequency | {len(recent_prod)} production deployments / 30 days | GitHub Deployments for configured production environments |
| Lead time for changes | {median_hours(lead_times)} | Commit timestamp to production deployment timestamp |
| Change failure rate | N/A | Requires an explicit production change-failure or rollback signal linked to a deployment |
| Mean time to restore | N/A | Requires incident start and service-restored timestamps |

DORA values are reported only when the repository contains the required production signals. Failed CI jobs or failed deployment attempts are not treated as production change failures.

## Data quality

- Sprint dates in docs/product/delivery-metrics-config.json are required for a time-based burndown.
- Story points are read from issue bodies using the Estimate: N SP field.
- Closed issues count as completed only when the team has accepted them under the Definition of Done.
- Change failure rate and mean time to restore remain N/A until production incident conventions are implemented.
"""
    OUTPUT_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
