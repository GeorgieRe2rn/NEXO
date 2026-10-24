import json
import re

import httpx

ua = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
}

with httpx.Client(timeout=30, headers=ua, follow_redirects=True) as c:
    r = c.get("https://fantasy.premierleague.com/api/bootstrap-static/")
    print("FPL", r.status_code, r.headers.get("content-type"))
    if r.status_code == 200:
        d = r.json()
        els = d.get("elements") or []
        print("  players", len(els))
        if els:
            p = els[0]
            print("  keys", list(p.keys()))
            print(
                "  sample",
                p.get("web_name"),
                "min",
                p.get("minutes"),
                "g",
                p.get("goals_scored"),
                "a",
                p.get("assists"),
                "starts",
                p.get("starts"),
                "yc",
                p.get("yellow_cards"),
                "photo",
                p.get("photo"),
            )

    for year in (2026, 2025):
        r = c.get(f"https://understat.com/league/EPL/{year}")
        print(f"understat EPL {year}", r.status_code, "len", len(r.text))
        m = re.search(r"playersData\s*=\s*JSON.parse\('(.*?)'\)", r.text)
        print("  playersData", bool(m))
        if m:
            raw = m.group(1).encode("utf-8").decode("unicode_escape")
            arr = json.loads(raw)
            print("  n", len(arr), "keys", list(arr[0].keys()) if arr else None)
            if arr:
                print(
                    "  sample",
                    {
                        k: arr[0].get(k)
                        for k in [
                            "player_name",
                            "team_title",
                            "games",
                            "time",
                            "goals",
                            "assists",
                            "shots",
                            "xG",
                            "yellow",
                        ]
                    },
                )
            break
