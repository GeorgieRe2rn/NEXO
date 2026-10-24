"""Transcripción de 41 selecciones visibles en capturas aportadas por el usuario.

Evidencia fechada del 15/10/2026: no es una conexión con Draftea ni momios actuales.
Los identificadores se cruzaron con los nombres, rivales y horarios de ESPN.
"""
import math

REFERENCE_DATE="2026-10-15"
ROWS=[
    ("401900450","Al-Faisaly",234),("401900902","Al Khaleej",112),("401900904","Al Hazm",147),
    ("401915854","Empate",216),("401915857","Empate",436),("401915858","KuPS",499),
    ("401915859","Midtjylland",-182),("401915748","Crvena Zvezda",174),("401915856","Borac Banja Luka",1176),
    ("401915855","Monaco",-204),("401915747","Kairat",290),("401915860","AGF Aarhus",380),
    ("401915861","Ajax",-159),("401915566","Empate",264),("401915567","Lillestrom",694),
    ("401915574","Real Sociedad",161),("401915575","Sunderland",-303),("401915577","Omonia Nicosia",151),
    ("401915568","Milan",100),("401915573","Hapoel Be'er Sheva",773),("401915576","Bayer Leverkusen",-175),
    ("401915565","Levski Sofia",286),("401915847","Lincoln Red Imps",1474),("401915560","Juventus",120),
    ("401915562","Celtic",909),("401915850","FC Nordsjaelland",126),("401915549","Anderlecht",257),
    ("401915563","Besiktas",241),("401915852","Sporting Braga",196),("401915561","Ararat-Armenia",608),
    ("401915571","Sturm Graz",1082),("401915849","Iberia 1999",962),("401915851","FC Thun",962),
    ("401915853","Kauno Zalgiris",4029),("401915848","FK Jablonec",1098),("401915746","Atalanta",-294),
    ("401915564","Viktoria Plzen",256),("401915550","Marseille",132),("401915572","Rennes",-476),
    ("401841622","Huracan",151),("401912523","Estudiantes",261),
]


def implied_probability(american):
    if not isinstance(american,(int,float)) or not math.isfinite(american) or abs(american)<100:
        raise ValueError("Momio americano inválido")
    return abs(american)/(abs(american)+100) if american<0 else 100/(american+100)


REFERENCES={event:{"pick":pick,"american_odds":odds,"implied_probability":implied_probability(odds),
    "date":REFERENCE_DATE,"source":"Capturas de Draftea aportadas por el usuario","live_verified":False,
    "note":"Probabilidad implícita del precio, con margen de la casa; no es una probabilidad validada del modelo ni una apuesta segura."} for event,pick,odds in ROWS}
