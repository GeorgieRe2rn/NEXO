from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from app.infrastructure.db.session import Base
from app.infrastructure.db.models import League, Team, Player
from app.services import roster_feed
from app.etl.calendar import utcnow


def test_extended_directory_and_stats_are_competition_scoped(monkeypatch):
    engine = create_engine('sqlite://')
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        db.add_all([League(code=code,name=code,country='Europa',season=utcnow().year) for code in ('CL','BL1')]); db.commit()
        def fake(url, params):
            slug = 'uefa.champions' if 'uefa.champions' in url else 'ger.1'
            if url.endswith('/teams'):
                return {'sports':[{'leagues':[{'slug':slug,'teams':[{'team':{'id':'132','displayName':'Bayern','logo':'https://example.org/bayern.png'}}]}]}]}
            if url.endswith('/scoreboard'):
                return {'leagues':[{'slug':slug,'logos':[{'href':'https://example.org/league.png'}]}]}
            return {'season':{'year':utcnow().year,'displayName':slug},'athletes':[{'id':'1','displayName':'Jugador','statistics':{'splits':{'categories':[{'stats':[{'name':'totalGoals','value':2 if slug=='uefa.champions' else 5,'displayValue':'2'},{'name':'minutesPlayed','value':0,'displayValue':''},{'name':'yellowCards','value':0,'displayValue':'0'}]}]}}}]}
        monkeypatch.setattr(roster_feed,'get_json',fake)
        result=roster_feed.sync_rosters(db,codes=('CL','BL1'))
        assert result['errors'] == 0
        assert result['players_updated'] == 2
        assert db.query(Team).count() == 2
        players=db.query(Player).order_by(Player.id).all()
        assert [p.season_stats['goals'] for p in players] == [2,5]
        assert all('minutes' not in p.season_stats for p in players)
        assert all(p.season_stats['yellows']==0 for p in players)
        assert all(p.photo_url is None for p in players)
        assert all(l.logo_url for l in db.query(League).all())
        monkeypatch.setattr(roster_feed,'get_json',lambda *args: (_ for _ in ()).throw(AssertionError('cache ignored')))
        assert roster_feed.sync_rosters(db,codes=('CL','BL1'))['teams_requested'] == 0
