"""Retirada solicitada: solo las ocho competiciones adicionales, con respaldo previo."""
import sqlite3
from pathlib import Path
from sqlalchemy import MetaData,select,delete
from app.infrastructure.db.session import engine
EXTRA=('EL','ECL','SPL','ARG','LIB','CL','BL','FL')
root=Path(__file__).resolve().parents[1]
backup=root/'data'/'forma-before-removing-extra-competitions.db'
if backup.exists(): raise RuntimeError('El respaldo ya existe; revisar antes de repetir.')
with sqlite3.connect(root/'data'/'forma.db') as src, sqlite3.connect(backup) as dest: src.backup(dest)
meta=MetaData();meta.reflect(bind=engine)
with engine.begin() as conn:
    leagues=meta.tables['leagues']
    targets=set(conn.scalars(select(leagues.c.id).where(leagues.c.code.in_(EXTRA))))
    doomed={'leagues':targets}
    while True:
        changed=False
        for table in meta.tables.values():
            pk=list(table.primary_key.columns)
            if len(pk)!=1: continue
            for fk in table.foreign_keys:
                parent=doomed.get(fk.column.table.name,set())
                if not parent: continue
                ids=set(conn.scalars(select(pk[0]).where(fk.parent.in_(parent))))
                before=len(doomed.get(table.name,set()))
                doomed.setdefault(table.name,set()).update(ids)
                changed |= len(doomed[table.name])!=before
        if not changed: break
    matches=meta.tables['matches']
    affected=doomed.get('matches',set())
    codes=set(conn.scalars(select(leagues.c.code).join(matches,matches.c.league_id==leagues.c.id).where(matches.c.id.in_(affected))))
    if not codes.issubset(set(EXTRA)): raise RuntimeError('Se detectaron partidos fuera del alcance autorizado.')
    print('Removal plan:',{k:len(v) for k,v in doomed.items() if v})
    for table in reversed(meta.sorted_tables):
        ids=doomed.get(table.name,set())
        if ids: conn.execute(delete(table).where(list(table.primary_key.columns)[0].in_(ids)))
    if 'feed_states' in meta.tables:
        conn.execute(delete(meta.tables['feed_states']).where(meta.tables['feed_states'].c.code.in_(EXTRA)))
    if 'api_cache' in meta.tables:
        conn.execute(delete(meta.tables['api_cache']).where(meta.tables['api_cache'].c.cache_key.like('catalog:%')))
print('Backup:',backup.name)
