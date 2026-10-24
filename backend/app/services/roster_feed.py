"""Plantillas actuales y cifras devueltas por ESPN, sin datos de demostración."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from app.domain.identity import map_position, nat_code, norm_name
from app.etl.calendar import parse_iso, utcnow
from app.infrastructure.db.models import ApiCache, League, Player, Team
from app.infrastructure.cache import cache_get, cache_put
from app.services.live_feed import BASE, get_json, number, resolve_team
from app.services.competition_registry import LEAGUES

from app.services.feed_lock import feed_lock as _lock
STATS = {"totalGoals":"goals","goalAssists":"assists","appearances":"played","totalShots":"shots","shotsOnTarget":"shots_on_target","yellowCards":"yellows","redCards":"reds","saves":"saves","goalsConceded":"goals_conceded","minutesPlayed":"minutes","starts":"lineups","cleanSheets":"clean_sheets"}
STATS.update({"foulsCommitted":"fouls", "foulsSuffered":"fouls_suffered", "ownGoals":"own_goals", "subIns":"sub_ins", "offsides":"offsides", "shotsFaced":"shots_faced"})


def sync_team_directory(db, codes, force=False):
    """Importa todos los clubes de la competición, aunque no jueguen esta jornada."""
    errors = 0
    for code in codes:
        league = db.query(League).filter_by(code=code).first()
        if not league:
            continue
        key = f"espn:directory:{code}"
        if not force and cache_get(db, key):
            continue
        try:
            data = get_json(f"{BASE}/{LEAGUES[code]}/teams", {"limit": 100})
            groups = [g for sport in data.get("sports", []) for g in sport.get("leagues", [])]
            group = next(g for g in groups if g.get("slug") == LEAGUES[code])
            members = group.get("teams") or []
            if not members or any(not (m.get("team") or {}).get("id") or not (m.get("team") or {}).get("displayName") for m in members):
                raise ValueError("Directorio incompleto")
            for member in members:
                resolve_team(db, league, member["team"])
            # Usa la URL del logo que devuelve la fuente, sin adivinar rutas.
            scoreboard = get_json(f"{BASE}/{LEAGUES[code]}/scoreboard", {})
            source_league = next((l for l in scoreboard.get("leagues", []) if l.get("slug") == LEAGUES[code]), {})
            logos = source_league.get("logos") or []
            if logos:
                league.logo_url = logos[0].get("href") or league.logo_url
            db.commit()
            cache_put(db, key, "espn", "teams", {"team_ids": [str(m["team"]["id"]) for m in members]}, ttl_hours=24)
        except Exception:
            db.rollback()
            errors += 1
    return errors


def sync_rosters(db, force=False, codes=None):
    if not _lock.acquire(blocking=False):
        return {"status":"busy"}
    try:
        now = utcnow()
        codes = tuple(code for code in (codes or LEAGUES) if code in LEAGUES)
        directory_errors = sync_team_directory(db, codes, force=force)
        teams = db.query(Team).filter(Team.espn_id.isnot(None)).all()
        jobs = []
        for t in teams:
            code = t.league.code
            if code not in codes:
                continue
            directory=db.get(ApiCache,f"espn:directory:{code}")
            members=set((directory.payload or {}).get("team_ids",[])) if directory else set()
            if members and str(t.espn_id) not in members:
                continue
            key = f"espn:roster:{code}:{t.espn_id}"
            cached = db.get(ApiCache, key)
            if not force and cached and parse_iso(cached.expires_at.isoformat()) > now:
                continue
            jobs.append((t.id,code,t.espn_id,key))
        def fetch(job):
            tid,code,ext,key = job
            try:
                return job,get_json(f"{BASE}/{LEAGUES[code]}/teams/{ext}/roster",{}),None
            except Exception as e:
                return job,None,type(e).__name__
        updated = 0
        errors = directory_errors
        with ThreadPoolExecutor(max_workers=4) as pool:
            for (tid,code,ext,key),data,error in pool.map(fetch,jobs):
                if error or not isinstance(data.get("athletes"),list):
                    errors += 1
                    continue
                # No acepta datos de una temporada vieja como plantilla actual.
                year = (data.get("season") or {}).get("year")
                if year is None or int(year) < now.year - (1 if now.month < 8 and code in {"PL","PD","SA","BL1","CL"} else 0):
                    errors += 1
                    continue
                people = db.query(Player).filter(Player.team_id==tid).all()
                by_name = {norm_name(p.name):p for p in people}
                for athlete in data["athletes"]:
                    if not athlete.get("displayName") or not athlete.get("id"):
                        continue
                    name = athlete["displayName"]
                    player = by_name.get(norm_name(name))
                    if not player:
                        player = Player(team_id=tid,name=name,external_id=-int(athlete["id"]))
                        db.add(player)
                    player.name = name
                    player.photo_url = (athlete.get("headshot") or {}).get("href")
                    player.position,player.position_label = map_position((athlete.get("position") or {}).get("name"))
                    player.date_of_birth = (athlete.get("dateOfBirth") or "")[:10] or None
                    player.age = int(number(athlete.get("age")) or 0)
                    player.height_cm = round(float(athlete["height"])*2.54) if athlete.get("height") else 0
                    player.weight_kg = round(float(athlete["weight"])*.453592) if athlete.get("weight") else 0
                    player.shirt_number = int(number(athlete.get("jersey")) or 0)
                    player.nationality = athlete.get("citizenship") or (athlete.get("birthPlace") or {}).get("country") or "—"
                    player.nationality_code = nat_code(player.nationality)
                    injuries = athlete.get("injuries") or []
                    player.injured = bool(injuries)
                    player.injury = (injuries[0].get("shortComment") or injuries[0].get("status")) if injuries else None
                    stats = {"source":"espn","verified_at":now.isoformat(),"season":year,"season_label":(data.get("season") or {}).get("displayName"),"espn_id":athlete["id"]}
                    for cat in ((athlete.get("statistics") or {}).get("splits") or {}).get("categories") or []:
                        for s in cat.get("stats") or []:
                            if s.get("name") in STATS and s.get("displayValue") not in (None, "", "--", "—"):
                                stats[STATS[s["name"]]] = number(s.get("value"))
                    player.season_stats = stats
                    updated += 1
                coaches = data.get("coach") or []
                if isinstance(coaches,list) and coaches:
                    db.get(Team,tid).coach_name = coaches[0].get("displayName")
                db.commit()
                cache_put(db,key,"espn","roster",{"updated":True},ttl_hours=24)
        return {"status":"ok" if errors==0 else "partial","players_updated":updated,"teams_requested":len(jobs),"errors":errors}
    finally:
        _lock.release()
