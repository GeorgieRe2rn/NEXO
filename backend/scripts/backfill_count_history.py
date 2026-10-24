"""Carga inicial acotada de córners/amarillas y verificación del alcance."""
import hashlib
import json
from pathlib import Path
from sqlalchemy import text
from app.etl.calendar import utcnow,display_window
from app.infrastructure.db.session import Base,engine,SessionLocal
from app.infrastructure.db.models import Match,League,CountObservation
from app.services.count_history import backfill_count_history
from app.services.competition_registry import LEAGUES
from app.services.forecasts import capture_forecasts,record_automatic_selections


def checksum(db,query):
    rows=[list(r) for r in db.execute(text(query))]
    return hashlib.sha256(json.dumps(rows,default=str,sort_keys=True).encode()).hexdigest()


def run():
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        queries={"result_and_goals":"select * from forecast_selections_v2 where market in ('result','goals') order by id", "predictions":"select * from predictions order by id", "match_stats":"select * from match_stats order by id", "matches":"select * from matches order by id"}
        before={k:checksum(db,q) for k,q in queries.items()}
        now=utcnow()
        matches=db.query(Match).join(League).filter(League.code.in_(tuple(LEAGUES)),Match.provider=="espn",Match.status=="SCHEDULED",Match.kickoff>now,Match.kickoff<display_window(now)[1]).all()
        report=backfill_count_history(db,matches,now,budget=600)
        report["observations_total"]=db.query(CountObservation).count()
        report["snapshots_created"]=capture_forecasts(db,matches)
        record_automatic_selections(db,matches,only_markets={"corners","yellows"})
        report["untouched"]={k:before[k]==checksum(db,q) for k,q in queries.items()}
        report["checked_at"]=utcnow().isoformat()
        Path("../docs/HISTORIAL_CORNERS_AMARILLAS.json").write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
        print(json.dumps(report,ensure_ascii=False),flush=True)
        if not all(report["untouched"].values()):raise RuntimeError("Se detectaron cambios fuera del alcance")


if __name__=="__main__":run()
