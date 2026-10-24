"""Quita jugadores duplicados y fotos que no coinciden con el id del jugador."""

from __future__ import annotations

import re
from collections import defaultdict

from sqlalchemy.orm import Session

from app.domain.identity import fold, norm_name
from app.infrastructure.db.models import Player, PlayerFormSnapshot, PlayerMatchStat, Team

_PHOTO_ID = re.compile(r"/players/(\d+)\.(png|jpg|jpeg|webp)", re.I)


_FOTMOB_ID = re.compile(r"/playerimages/(\d+)\.(png|jpg|jpeg|webp)", re.I)


def photo_matches_player(player: Player) -> bool:
    if not player.photo_url or not player.external_id:
        return False
    url = player.photo_url
    eid = int(player.external_id)
    m = _PHOTO_ID.search(url) or _FOTMOB_ID.search(url)
    if not m:
        return False
    return int(m.group(1)) == eid


def _score(p: Player) -> tuple:
    stats = p.season_stats or {}
    return (
        1 if photo_matches_player(p) else 0,
        1 if stats else 0,
        int(stats.get("minutes") or 0),
        int(stats.get("played") or 0),
        int(stats.get("goals") or 0),
        1 if p.shirt_number else 0,
        p.id or 0,
    )


def _name_key(name: str) -> str:
    parts = [p for p in re.split(r"[\s.]+", fold(name)) if p]
    if not parts:
        return ""
    return f"{parts[0][0]}|{parts[-1]}"


def dedupe_and_sanitize_photos(db: Session) -> dict:
    moved_stats = moved_form = deleted = stripped = 0
    for team in db.query(Team).all():
        groups: dict[str, list[Player]] = defaultdict(list)
        for p in db.query(Player).filter(Player.team_id == team.id).all():
            groups[_name_key(p.name) or norm_name(p.name)].append(p)
        for _name, pack in groups.items():
            if len(pack) < 2:
                continue
            pack.sort(key=_score, reverse=True)
            keep, extras = pack[0], pack[1:]
            for extra in extras:
                db.query(PlayerMatchStat).filter(PlayerMatchStat.player_id == extra.id).update(
                    {PlayerMatchStat.player_id: keep.id}
                )
                db.query(PlayerFormSnapshot).filter(PlayerFormSnapshot.player_id == extra.id).update(
                    {PlayerFormSnapshot.player_id: keep.id}
                )
                if extra.season_stats and not keep.season_stats:
                    keep.season_stats = extra.season_stats
                if extra.shirt_number and not keep.shirt_number:
                    keep.shirt_number = extra.shirt_number
                db.delete(extra)
                deleted += 1
                moved_stats += 1
    for p in db.query(Player).all():
        if p.photo_url and not photo_matches_player(p):
            p.photo_url = None
            stripped += 1
    db.commit()
    return {"deleted_duplicates": deleted, "photos_removed_unsafe": stripped, "stats_retargeted": moved_stats}


def run_cleanup(db: Session) -> dict:
    return dedupe_and_sanitize_photos(db)
