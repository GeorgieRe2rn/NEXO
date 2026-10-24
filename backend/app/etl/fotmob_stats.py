"""Plantillas + estadísticas individuales desde FotMob (gratis, por id de jugador).

Unifica H. Martín / Henry Martín y descarta clones de otro club (R. Alvarado en América).
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy.orm.attributes import flag_modified

from app.domain.identity import fold, nat_code
from app.etl.cleanup import photo_matches_player
from app.infrastructure.db.models import EtlRun, League, Match, Player, PlayerFormSnapshot, PlayerMatchStat, Team
from app.infrastructure.providers.fotmob import PER90_SET, STAT_FILES, FotmobProvider

logger = logging.getLogger(__name__)

PHOTO = "https://images.fotmob.com/image_resources/playerimages/{}.png"

STOP = {"fc", "cf", "afc", "sc", "ac", "cd", "the", "de", "club", "calcio", "sad", "ssc", "us"}

# Clave canónica para no cruzar Chivas con Chicago Fire ni Inter Miami con Inter.
ALIASES = {
    "america": "america",
    "cf america": "america",
    "club america": "america",
    "chivas": "chivas",
    "chivas guadalajara": "chivas",
    "guadalajara chivas": "chivas",
    "cd guadalajara": "chivas",
    "deportivo guadalajara": "chivas",
    "guadalajara": "chivas",
    "chicago fire": "chicago fire",
    "chicago fire fc": "chicago fire",
    "inter miami": "inter miami",
    "inter miami cf": "inter miami",
    "internazionale": "inter milan",
    "internazionale milano": "inter milan",
    "fc internazionale milano": "inter milan",
    "inter milan": "inter milan",
    "inter": "inter milan",
    "atletico madrid": "atletico madrid",
    "atletico de madrid": "atletico madrid",
    "club atletico de madrid": "atletico madrid",
    "athletic": "athletic club",
    "athletic club": "athletic club",
    "athletic bilbao": "athletic club",
    "real sociedad": "real sociedad",
    "real sociedad de futbol": "real sociedad",
    "manchester city": "manchester city",
    "manchester united": "manchester united",
    "tottenham": "tottenham",
    "tottenham hotspur": "tottenham",
    "wolves": "wolves",
    "wolverhampton wanderers": "wolves",
    "brighton": "brighton",
    "brighton hove albion": "brighton",
    "nottingham forest": "nottingham forest",
    "newcastle": "newcastle",
    "newcastle united": "newcastle",
    "west ham": "west ham",
    "west ham united": "west ham",
    "lafc": "lafc",
    "los angeles fc": "lafc",
    "galaxy": "galaxy",
    "la galaxy": "galaxy",
    "los angeles galaxy": "galaxy",
    "nycfc": "nycfc",
    "new york city": "nycfc",
    "new york city fc": "nycfc",
    "atlanta": "atlanta united",
    "atlanta united": "atlanta united",
    "atlanta united fc": "atlanta united",
    "seattle": "seattle",
    "seattle sounders": "seattle",
    "seattle sounders fc": "seattle",
    "monterrey": "monterrey",
    "cf monterrey": "monterrey",
    "rayados monterrey": "monterrey",
    "tigres": "tigres",
    "tigres uanl": "tigres",
    "uanl tigres": "tigres",
    "pumas": "pumas",
    "pumas unam": "pumas",
    "club universidad nacional": "pumas",
    "cruz azul": "cruz azul",
    "juarez": "juarez",
    "fc juarez": "juarez",
    "leon": "leon",
    "club leon": "leon",
    "queretaro": "queretaro",
    "club queretaro": "queretaro",
    "queretaro fc": "queretaro",
    "tijuana": "tijuana",
    "xolos tijuana": "tijuana",
    "club tijuana": "tijuana",
    "san luis": "san luis",
    "atletico de san luis": "san luis",
    "atletico san luis": "san luis",
    "santos": "santos",
    "santos laguna": "santos",
    "club santos laguna": "santos",
    "mazatlan": "mazatlan",
    "mazatlan fc": "mazatlan",
    "milan": "milan",
    "ac milan": "milan",
    "roma": "roma",
    "as roma": "roma",
    "lazio": "lazio",
    "ss lazio": "lazio",
    "napoli": "napoli",
    "ssc napoli": "napoli",
    "juventus": "juventus",
    "bournemouth": "bournemouth",
    "afc bournemouth": "bournemouth",
    "leeds": "leeds",
    "leeds united": "leeds",
    "sunderland": "sunderland",
    "sunderland afc": "sunderland",
    "burnley": "burnley",
    "crystal palace": "crystal palace",
    "fulham": "fulham",
    "brentford": "brentford",
    "everton": "everton",
    "aston villa": "aston villa",
    "arsenal": "arsenal",
    "chelsea": "chelsea",
    "liverpool": "liverpool",
    "barcelona": "barcelona",
    "real madrid": "real madrid",
    "girona": "girona",
    "sevilla": "sevilla",
    "valencia": "valencia",
    "villarreal": "villarreal",
    "celta": "celta",
    "celta vigo": "celta",
    "rc celta": "celta",
    "betis": "betis",
    "real betis": "betis",
    "osasuna": "osasuna",
    "mallorca": "mallorca",
    "getafe": "getafe",
    "alaves": "alaves",
    "deportivo alaves": "alaves",
    "rayo vallecano": "rayo vallecano",
    "espanyol": "espanyol",
    "levante": "levante",
    "elche": "elche",
    "oviedo": "oviedo",
    "real oviedo": "oviedo",
    "real racing": "racing santander",
    "racing santander": "racing santander",
    "real racing club de santander": "racing santander",
}

ROLE_POS = {
    "keeper": ("GK", "Portero"),
    "keeper_long": ("GK", "Portero"),
    "goalkeeper": ("GK", "Portero"),
    "defender": ("DF", "Defensa"),
    "defender_long": ("DF", "Defensa"),
    "midfielder": ("MF", "Mediocampista"),
    "midfielder_long": ("MF", "Mediocampista"),
    "attacker": ("FW", "Delantero"),
    "attacker_long": ("FW", "Delantero"),
    "forward": ("FW", "Delantero"),
}
GROUP_POS = {
    "keepers": ("GK", "Portero"),
    "goalkeepers": ("GK", "Portero"),
    "defenders": ("DF", "Defensa"),
    "midfielders": ("MF", "Mediocampista"),
    "attackers": ("FW", "Delantero"),
}


def name_key(name: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", fold(name)) if p]
    if not parts:
        return ""
    return f"{parts[0][0]}|{parts[-1]}"


def _tokens(name: str) -> list[str]:
    n = fold(name).replace("-", " ")
    n = re.sub(r"[^a-z0-9\s]", " ", n)
    return [t for t in n.split() if t and t not in STOP]


def canon_team(name: str) -> str:
    toks = _tokens(name)
    s = " ".join(toks)
    return ALIASES.get(s, s)


def match_team(
    fm_name: str,
    fm_short: str,
    teams: list[Team],
    preferred_ids: set[int] | None = None,
) -> Team | None:
    keys = {canon_team(fm_name), canon_team(fm_short)} - {""}
    scored: list[tuple[int, Team]] = []
    for team in teams:
        ours = {canon_team(team.name), canon_team(team.short_name)} - {""}
        if keys & ours:
            scored.append((100, team))
            continue
        ft = set(_tokens(fm_name) + _tokens(fm_short))
        ot = set(_tokens(team.name) + _tokens(team.short_name))
        if not ft or not ot:
            continue
        if ft == ot:
            scored.append((90, team))
        elif ft <= ot or ot <= ft:
            scored.append((70, team))
        else:
            inter = ft & ot
            if len(inter) >= 2:
                scored.append((60, team))
    if not scored:
        return None
    scored.sort(key=lambda x: x[0], reverse=True)
    best = scored[0][0]
    winners = [t for s, t in scored if s == best]
    unique: list[Team] = []
    seen = set()
    for t in winners:
        if t.id not in seen:
            unique.append(t)
            seen.add(t.id)
    if len(unique) == 1:
        return unique[0]
    preferred_ids = preferred_ids or set()
    unique.sort(key=lambda t: (0 if t.id in preferred_ids else 1, t.id or 0))
    logger.info("FotMob equipo duplicado %s → se usa %s", fm_name, unique[0].name)
    return unique[0]


def _merge_player(keep: Player, extra: Player, db: Session) -> None:
    db.query(PlayerMatchStat).filter(PlayerMatchStat.player_id == extra.id).update(
        {PlayerMatchStat.player_id: keep.id}, synchronize_session=False
    )
    db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.player_id == extra.id).update(
        {PlayerFormSnapshot.player_id: keep.id}, synchronize_session=False
    )
    extra_stats = extra.season_stats or {}
    keep_stats = dict(keep.season_stats or {})
    if extra_stats:
        extra_min = int(extra_stats.get("minutes") or 0)
        keep_min = int(keep_stats.get("minutes") or 0)
        if extra_min > keep_min or (extra_stats and not keep_stats):
            keep_stats.update(extra_stats)
            keep.season_stats = keep_stats
            flag_modified(keep, "season_stats")
    if extra.shirt_number and not keep.shirt_number:
        keep.shirt_number = extra.shirt_number
    if extra.age and not keep.age:
        keep.age = extra.age
    if extra.nationality and extra.nationality != "—":
        keep.nationality = extra.nationality
        keep.nationality_code = extra.nationality_code
    extra_first = (extra.name or "").replace(".", " ").split()[:1]
    keep_first = (keep.name or "").replace(".", " ").split()[:1]
    extra_full = bool(extra_first) and len(extra_first[0]) > 2
    keep_abbrev = bool(keep_first) and len(keep_first[0]) <= 2
    if extra_full and (keep_abbrev or len(extra.name) > len(keep.name)):
        keep.name = extra.name
    db.delete(extra)


def merge_initial_duplicates(db: Session) -> int:
    """Une 'H. Martín' con 'Henry Martín' en el mismo club."""
    deleted = 0
    for team in db.query(Team).all():
        groups: dict[str, list[Player]] = defaultdict(list)
        for p in db.query(Player).filter(Player.team_id == team.id).all():
            groups[name_key(p.name)].append(p)
        for key, pack in groups.items():
            if len(pack) < 2 or not key:
                continue

            def _abbrev(name: str) -> bool:
                token = (name or "").replace(".", " ").split()[:1]
                return bool(token) and len(token[0]) <= 2

            pack.sort(
                key=lambda p: (
                    1 if (p.season_stats or {}).get("source") == "fotmob" else 0,
                    1 if _abbrev(p.name) and photo_matches_player(p) else 0,
                    1 if photo_matches_player(p) else 0,
                    int((p.season_stats or {}).get("minutes") or 0),
                    p.id or 0,
                ),
                reverse=True,
            )
            keep = pack[0]
            for extra in pack[1:]:
                _merge_player(keep, extra, db)
                deleted += 1
    db.commit()
    return deleted


def _to_int(val) -> int:
    try:
        return int(round(float(val or 0)))
    except (TypeError, ValueError):
        return 0


def _to_float(val):
    try:
        return round(float(val), 2)
    except (TypeError, ValueError):
        return None


def _per90_total(per90, minutes: int) -> int:
    if not minutes:
        return 0
    try:
        return int(round(float(per90 or 0) * minutes / 90.0))
    except (TypeError, ValueError):
        return 0


def load_stats_by_id(fm: FotmobProvider, path: str) -> dict[int, dict]:
    by_id: dict[int, dict] = {}
    for filename in STAT_FILES:
        for row in fm.stat_list(path, filename):
            pid = row.get("ParticiantId")
            if pid is None:
                continue
            pid = int(pid)
            bucket = by_id.setdefault(
                pid,
                {
                    "name": row.get("ParticipantName") or "",
                    "team": row.get("TeamName") or "",
                    "fotmob_id": pid,
                    "fotmob_team_id": row.get("TeamId"),
                    "minutes": int(row.get("MinutesPlayed") or 0),
                    "played": int(row.get("MatchesPlayed") or 0),
                },
            )
            val = row.get("StatValue")
            mins = int(row.get("MinutesPlayed") or bucket.get("minutes") or 0)
            played = int(row.get("MatchesPlayed") or bucket.get("played") or 0)
            if mins:
                bucket["minutes"] = mins
            if played:
                bucket["played"] = played
            if filename == "mins_played":
                bucket["minutes"] = _to_int(val or mins)
                bucket["played"] = played or bucket["played"]
            elif filename == "goals":
                bucket["goals"] = _to_int(val)
            elif filename == "goal_assist":
                bucket["assists"] = _to_int(val)
            elif filename == "rating":
                bucket["rating"] = _to_float(val)
            elif filename == "yellow_card":
                bucket["yellows"] = _to_int(val)
            elif filename == "red_card":
                bucket["reds"] = _to_int(val)
            elif filename == "expected_goals":
                bucket["xg"] = _to_float(val)
            elif filename == "expected_assists":
                bucket["xa"] = _to_float(val)
            elif filename == "big_chance_created":
                bucket["key_passes"] = _to_int(val)
            elif filename == "clean_sheet":
                bucket["clean_sheets"] = _to_int(val)
            elif filename == "penalty_won":
                bucket["penalties"] = _to_int(val)
            elif filename in PER90_SET:
                total = _per90_total(val, mins)
                if filename == "total_scoring_att":
                    bucket["shots"] = total
                elif filename == "ontarget_scoring_att":
                    bucket["shots_on_target"] = total
                elif filename == "accurate_pass":
                    bucket["passes"] = total
                elif filename == "saves":
                    bucket["saves"] = total
                elif filename == "fouls":
                    bucket["fouls"] = total
                elif filename == "total_tackle":
                    bucket["tackles"] = total
                elif filename == "interception":
                    bucket["interceptions"] = total
    return by_id


def _position(member: dict) -> tuple[str, str]:
    role = member.get("role") or {}
    key = (role.get("key") or "").lower()
    if key in ROLE_POS:
        return ROLE_POS[key]
    group = (member.get("_group") or "").lower()
    if group in GROUP_POS:
        return GROUP_POS[group]
    return "MF", role.get("fallback") or "Mediocampista"


def _injury_text(raw) -> str | None:
    if not raw:
        return None
    if isinstance(raw, str):
        return raw[:160]
    if isinstance(raw, dict):
        for k in ("reason", "name", "description", "title", "type"):
            if raw.get(k):
                return str(raw[k])[:160]
        return "Lesión"
    return "Lesión"


def _has_match_trace(player: Player, db: Session) -> bool:
    if db.query(PlayerMatchStat.id).filter(PlayerMatchStat.player_id == player.id).first():
        return True
    if db.query(PlayerFormSnapshot.id).filter(PlayerFormSnapshot.player_id == player.id).first():
        return True
    return False


def _apply_identity(player: Player, member: dict, stats: dict) -> None:
    fid = int(member["id"])
    player.name = member.get("name") or player.name
    player.external_id = fid
    player.photo_url = PHOTO.format(fid)
    pos, label = _position(member)
    player.position = pos
    player.position_label = label
    if member.get("cname"):
        player.nationality = member["cname"]
        player.nationality_code = nat_code(member.get("cname"))
    if member.get("dateOfBirth"):
        player.date_of_birth = str(member["dateOfBirth"])[:16]
    if member.get("age"):
        player.age = int(member["age"])
    if member.get("height"):
        player.height_cm = int(member["height"])
    shirt = member.get("shirtNumber")
    if shirt not in (None, ""):
        player.shirt_number = int(shirt)
    inj = _injury_text(member.get("injury"))
    player.injured = bool(inj)
    player.injury = inj
    payload = dict(player.season_stats or {})
    payload.update(
        {
            "goals": stats.get("goals", 0),
            "assists": stats.get("assists", 0),
            "played": stats.get("played", 0),
            "minutes": stats.get("minutes", 0),
            "rating": stats.get("rating"),
            "shots": stats.get("shots", 0),
            "shots_on_target": stats.get("shots_on_target", 0),
            "yellows": stats.get("yellows", 0),
            "reds": stats.get("reds", 0),
            "xg": stats.get("xg"),
            "xa": stats.get("xa"),
            "key_passes": stats.get("key_passes", 0),
            "clean_sheets": stats.get("clean_sheets", 0),
            "penalties": stats.get("penalties", payload.get("penalties", 0)),
            "passes": stats.get("passes", 0),
            "saves": stats.get("saves", 0),
            "fouls": stats.get("fouls", 0),
            "tackles": stats.get("tackles", 0),
            "interceptions": stats.get("interceptions", 0),
            "lineups": stats.get("played", 0),
            "fotmob_id": fid,
            "source": "fotmob",
        }
    )
    player.season_stats = payload
    flag_modified(player, "season_stats")


def apply_fotmob(db: Session, fm: FotmobProvider) -> dict:
    updated = created = deleted = unmatched_teams = 0
    for code in ("PL", "PD", "SA", "MLS", "MX"):
        league = db.query(League).filter(League.code == code).one_or_none()
        if not league:
            continue
        path = fm.season_path(code)
        if not path:
            logger.warning("FotMob sin temporada para %s", code)
            continue
        stats_by_id = load_stats_by_id(fm, path)
        our_teams = db.query(Team).filter(Team.league_id == league.id).all()
        preferred_ids = {
            row[0]
            for row in db.query(Match.home_team_id).filter(Match.league_id == league.id).all()
        } | {
            row[0]
            for row in db.query(Match.away_team_id).filter(Match.league_id == league.id).all()
        }
        fm_teams = fm.league_teams(code)
        matched_team_ids: set[int] = set()
        for fm_team in fm_teams:
            team = match_team(fm_team["name"], fm_team["shortName"], our_teams, preferred_ids)
            if team is None:
                unmatched_teams += 1
                logger.warning("Sin club local para FotMob %s (%s)", fm_team["name"], code)
                continue
            if team.id in matched_team_ids:
                logger.warning("Club ya emparejado, se omite %s → %s", fm_team["name"], team.name)
                continue
            matched_team_ids.add(team.id)
            roster = db.query(Player).filter(Player.team_id == team.id).all()
            by_ext: dict[int, list[Player]] = defaultdict(list)
            by_nk: dict[str, list[Player]] = defaultdict(list)
            for p in roster:
                if p.external_id:
                    by_ext[int(p.external_id)].append(p)
                by_nk[name_key(p.name)].append(p)

            keep_ids: set[int] = set()
            try:
                squad = fm.team_squad(fm_team["id"])
            except Exception:
                logger.exception("No se pudo leer plantilla FotMob %s", fm_team["name"])
                continue
            if not squad:
                logger.warning("Plantilla FotMob vacía para %s", fm_team["name"])
                continue

            for member in squad:
                fid = int(member["id"])
                nk = name_key(member.get("name") or "")
                cands = list(by_ext.get(fid) or [])
                if not cands and nk:
                    cands = list(by_nk.get(nk) or [])
                player = None
                if cands:
                    cands.sort(
                        key=lambda p: (
                            1 if p.external_id == fid else 0,
                            1 if photo_matches_player(p) else 0,
                            int((p.season_stats or {}).get("minutes") or 0),
                            p.id or 0,
                        ),
                        reverse=True,
                    )
                    player = cands[0]
                    for extra in cands[1:]:
                        if extra.id == player.id:
                            continue
                        _merge_player(player, extra, db)
                        roster = [x for x in roster if x.id != extra.id]
                if player is None:
                    player = Player(
                        team_id=team.id,
                        name=member.get("name") or "Jugador",
                        position="MF",
                        nationality="—",
                        nationality_code=nat_code(member.get("cname")),
                    )
                    db.add(player)
                    db.flush()
                    roster.append(player)
                    created += 1
                _apply_identity(player, member, stats_by_id.get(fid) or {})
                keep_ids.add(player.id)
                by_ext[fid] = [player]
                if nk:
                    by_nk[nk] = [player]
                updated += 1

            keepers = {
                p.id: p
                for p in db.query(Player).filter(Player.team_id == team.id, Player.id.in_(keep_ids)).all()
            } if keep_ids else {}
            keep_by_nk = {name_key(p.name): p for p in keepers.values() if name_key(p.name)}
            for leftover in list(db.query(Player).filter(Player.team_id == team.id).all()):
                if leftover.id in keep_ids:
                    continue
                mate = keep_by_nk.get(name_key(leftover.name))
                if mate is not None:
                    _merge_player(mate, leftover, db)
                    deleted += 1
                    continue
                if _has_match_trace(leftover, db):
                    if leftover.photo_url and not photo_matches_player(leftover):
                        leftover.photo_url = None
                    continue
                db.query(PlayerMatchStat).filter(PlayerMatchStat.player_id == leftover.id).delete(
                    synchronize_session=False
                )
                db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.player_id == leftover.id).delete(
                    synchronize_session=False
                )
                db.delete(leftover)
                deleted += 1
            db.commit()
            logger.info("FotMob %s %s squad=%s", code, team.short_name, len(keep_ids))
        logger.info("FotMob %s updated=%s created=%s deleted=%s", code, updated, created, deleted)
    return {"updated": updated, "created": created, "deleted": deleted, "unmatched_teams": unmatched_teams}


def strip_unsafe_photos(db: Session) -> int:
    n = 0
    for p in db.query(Player).all():
        if p.photo_url and not photo_matches_player(p):
            p.photo_url = None
            n += 1
    db.commit()
    return n


def run_fotmob_stats(db: Session) -> dict:
    run = EtlRun(started_at=datetime.now(timezone.utc), status="running", source="fotmob")
    db.add(run)
    db.commit()
    fm = FotmobProvider(db)
    try:
        merged = merge_initial_duplicates(db)
        counts = apply_fotmob(db, fm)
        merged += merge_initial_duplicates(db)
        stripped = strip_unsafe_photos(db)
        run.status = "ok"
        run.finished_at = datetime.now(timezone.utc)
        run.requests_made = fm.requests_made
        run.cache_hits = fm.cache_hits
        run.rows_upserted = counts["updated"]
        run.notes = (
            f"fotmob={counts['updated']} created={counts['created']} "
            f"deleted={counts['deleted']} merged={merged} photos_stripped={stripped} "
            f"unmatched_teams={counts['unmatched_teams']}"
        )
        db.commit()
        return {
            "status": "ok",
            "players": counts["updated"],
            "created": counts["created"],
            "deleted": counts["deleted"],
            "merged": merged,
            "photos_stripped": stripped,
            "unmatched_teams": counts["unmatched_teams"],
            "requests_made": fm.requests_made,
            "cache_hits": fm.cache_hits,
        }
    except Exception as exc:
        logger.exception("fotmob stats failed")
        run.status = "error"
        run.finished_at = datetime.now(timezone.utc)
        run.notes = str(exc)
        db.commit()
        raise
