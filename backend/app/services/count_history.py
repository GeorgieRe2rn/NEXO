"""Historial publicado exclusivamente para córners y amarillas.

No escribe MatchStat, marcadores, xG, forma ni Prediction.
"""
import logging
import math
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from sqlalchemy import or_
from app.etl.calendar import aware, parse_iso, kickoff_iso
from app.infrastructure.cache import cache_get, cache_put
from app.infrastructure.db.models import CountObservation, Match
from app.services.competition_registry import LEAGUES

logger = logging.getLogger(__name__)
FIELDS = {"wonCorners":"corners", "yellowCards":"yellows"}


def counter(value):
    try:
        number=float(value)
        return int(number) if not isinstance(value,bool) and math.isfinite(number) and number >= 0 and number.is_integer() else None
    except (TypeError,ValueError): return None


def store_summary(db, match, data, now):
    header=data.get("header") or {}
    comp=(header.get("competitions") or [{}])[0]
    kind=(comp.get("status") or {}).get("type") or {}
    if str(header.get("id")) != str(match.provider_id): raise ValueError("Resumen de otro partido")
    if not kind.get("completed") or kind.get("state") != "post" or int((comp.get("status") or {}).get("period") or 2)>2:
        raise ValueError("Sin final confirmado a tiempo reglamentario")
    if (header.get("league") or {}).get("slug") != LEAGUES.get(match.league.code):
        raise ValueError("Competición distinta")
    source_date=comp.get("date") or header.get("date")
    if not source_date or parse_iso(source_date)!=aware(match.kickoff) or aware(match.kickoff)>=now:
        raise ValueError("Fecha no verificable")
    expected={"home":str(match.home_team.espn_id),"away":str(match.away_team.espn_id)}
    competitors={t.get("homeAway"):str((t.get("team") or {}).get("id")) for t in comp.get("competitors") or []}
    if any(competitors.get(side)!=tid for side,tid in expected.items()): raise ValueError("Equipos distintos")
    values={}
    for team in (data.get("boxscore") or {}).get("teams") or []:
        tid=str((team.get("team") or {}).get("id"))
        side=next((s for s,i in expected.items() if i==tid),None)
        if side:
            for stat in team.get("statistics") or []:
                if stat.get("name") in FIELDS:
                    values[f"{side}_{FIELDS[stat['name']]}"]=counter(stat.get("displayValue"))
    row=db.get(CountObservation,match.id)
    if row is None:
        row=CountObservation(match_id=match.id)
        db.add(row)
    for side in ("home","away"):
        for key in ("corners","yellows"):
            setattr(row,f"{side}_{key}",values.get(f"{side}_{key}"))
    row.checked_at=now
    row.source_url=f"https://www.espn.com/soccer/match/_/gameId/{match.provider_id}"
    db.flush()
    return row


def history_rows(db, match, market):
    """Cinco antecedentes por equipo, anteriores al encuentro, con ambos contadores."""
    rows=db.query(Match,CountObservation).outerjoin(CountObservation,CountObservation.match_id==Match.id).filter(
        Match.league_id==match.league_id,Match.provider=="espn",Match.status=="FINISHED",
        Match.id!=match.id,Match.kickoff<match.kickoff,
        Match.kickoff>=aware(match.kickoff)-timedelta(days=365)).order_by(Match.kickoff.desc()).all()
    result=[];coverage={}
    for side,tid in (("home",match.home_team_id),("away",match.away_team_id)):
        team_rows=[]
        for previous,observation in rows:
            if tid not in (previous.home_team_id,previous.away_team_id): continue
            if observation:
                values=[getattr(observation,f"{s}_{market}") for s in ("home","away")]
                source=observation.source_url;checked=observation.checked_at
            else:
                live=previous.live_data or {}
                if not live.get("final_details"): continue
                stats=live.get("stats") or {}
                values=[counter((stats.get(s) or {}).get(market)) for s in ("home","away")]
                source=f"https://www.espn.com/soccer/match/_/gameId/{previous.provider_id}"
                checked=previous.verified_at
            if any(v is None for v in values):continue
            team_rows.append({"match_id":previous.id,"provider_id":previous.provider_id,"kickoff":kickoff_iso(previous.kickoff),
                "home":previous.home_team.name,"away":previous.away_team.name,"home_value":values[0],"away_value":values[1],
                "total":sum(values),"source_url":source,"checked_at":kickoff_iso(checked)})
            if len(team_rows)==5:break
        coverage[side]=len(team_rows)
        result.extend(team_rows)
    unique={r["match_id"]:r for r in result}
    return list(unique.values()),coverage


def backfill_count_history(db, matches, now, budget=24):
    from app.services.live_feed import BASE,get_json
    jobs={}
    seen_teams=set()
    targets=sorted([m for m in matches if m.status in {"SCHEDULED","LIVE"} and m.league.code in LEAGUES],key=lambda m:aware(m.kickoff))
    for match in targets:
        for team in (match.home_team,match.away_team):
            if not team.espn_id:continue
            if team.id in seen_teams:continue
            seen_teams.add(team.id)
            history=db.query(Match).filter(Match.league_id==match.league_id,Match.provider=="espn",Match.provider_id.isnot(None),
                Match.status=="FINISHED",Match.kickoff<min(aware(match.kickoff),now),Match.kickoff>=now-timedelta(days=365),
                or_(Match.home_team_id==team.id,Match.away_team_id==team.id)).order_by(Match.kickoff.desc()).limit(12).all()
            completed=0
            for past in history:
                observation=db.get(CountObservation,past.id)
                if observation and now-aware(observation.checked_at)<timedelta(hours=24):
                    if all(getattr(observation,f"{s}_{k}") is not None for s in ("home","away") for k in ("corners","yellows")):
                        completed+=1
                    if completed>=5:break
                    continue
                if cache_get(db,f"counts:retry:{past.provider_id}"):continue
                # Relaciones cargadas en el hilo de la sesión, solo HTTP en trabajadores.
                _=past.home_team.espn_id,past.away_team.espn_id,past.league.code
                jobs.setdefault(past.id,(past.id,past.provider_id,past.league.code))
                completed+=1
                if completed>=5:break
    chosen=list(jobs.values())[:budget]
    def fetch(job):
        mid,pid,code=job
        try:return mid,get_json(f"{BASE}/{LEAGUES[code]}/summary",{"event":pid}),None
        except Exception as exc:return mid,None,type(exc).__name__
    stored=failed=0
    with ThreadPoolExecutor(max_workers=4) as pool:
        for mid,data,error in pool.map(fetch,chosen):
            past=db.get(Match,mid)
            try:
                if error:raise ValueError(error)
                with db.begin_nested():store_summary(db,past,data,now)
                stored+=1
            except (ValueError,TypeError,KeyError):
                cache_put(db,f"counts:retry:{past.provider_id}","espn","summary",{"unavailable":True},ttl_hours=6)
                failed+=1
    db.commit()
    return {"requested":len(chosen),"stored":stored,"unavailable":failed,"remaining":max(0,len(jobs)-len(chosen))}
