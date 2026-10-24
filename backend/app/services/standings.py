"""Clasificaciones publicadas; independientes de los partidos parciales locales."""
from datetime import timedelta
import logging
from fastapi import HTTPException
from app.etl.calendar import aware, utcnow
from app.infrastructure.db.models import ApiCache, Team, League
from app.services.competition_registry import LEAGUES
from app.services.live_feed import get_json

logger = logging.getLogger(__name__)


def parse_standings(payload):
    groups = []
    def visit(node):
        table = node.get('standings') or {}
        entries = table.get('entries') or []
        if entries:
            rows = []
            columns = {}
            for entry in entries:
                team = entry.get('team') or {}
                stats = {}
                for stat in entry.get('stats') or []:
                    name = stat.get('name')
                    if not name:
                        continue
                    columns.setdefault(name, {'key': name, 'label': stat.get('displayName') or name, 'description': stat.get('description') or ''})
                    # An empty displayValue is absent, even if the API supplies a placeholder value.
                    stats[name] = stat.get('displayValue') or None
                rows.append({'id': team.get('id'), 'name': team.get('displayName') or team.get('name'), 'logo': next((x.get('href') for x in team.get('logos', []) if x.get('href')), None), 'stats': stats})
            groups.append({'name': node.get('name') or table.get('displayName'), 'season': table.get('seasonDisplayName'), 'columns': list(columns.values()), 'rows': rows})
        for child in node.get('children') or []:
            visit(child)
    visit(payload)
    if not groups:
        raise ValueError('La fuente no publicó una clasificación')
    return groups


def league_standings(db, code):
    if code not in LEAGUES:
        raise HTTPException(404, 'Liga no disponible')
    now = utcnow()
    key = f'espn:standings:{code}'
    cached = db.get(ApiCache, key)
    stale = False
    if not cached or aware(cached.expires_at) <= now:
        try:
            url = f'https://site.api.espn.com/apis/v2/sports/soccer/{LEAGUES[code]}/standings'
            payload = get_json(url, {})
            parse_standings(payload)
            if not cached:
                cached = ApiCache(cache_key=key, provider='espn', endpoint=url)
                db.add(cached)
            cached.payload = payload
            cached.fetched_at = now
            cached.expires_at = now + timedelta(minutes=5)
            db.commit()
        except Exception:
            db.rollback()
            logger.warning('No se pudo actualizar la tabla de %s', code)
            if not cached:
                raise HTTPException(503, 'La clasificación no está disponible. Intenta de nuevo más tarde.')
            stale = True
    groups = parse_standings(cached.payload)
    teams = {str(t.espn_id): t.id for t in db.query(Team).join(League).filter(League.code == code, Team.espn_id.isnot(None)).all()}
    for group in groups:
        for row in group['rows']:
            row['team_id'] = teams.get(str(row['id']))
    return {'league': code, 'source': 'ESPN', 'source_url': f'https://www.espn.com/soccer/table/_/league/{LEAGUES[code]}', 'fetched_at': aware(cached.fetched_at).isoformat(), 'stale': stale, 'groups': groups}
