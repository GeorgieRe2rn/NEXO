CORE_LEAGUES={"MX":"mex.1","PL":"eng.1","PD":"esp.1","SA":"ita.1","MLS":"usa.1"}
EXTENDED_COMPETITIONS={
    "CL": ("uefa.champions", "UEFA Champions League", "Europa"),
    "BL1": ("ger.1", "Bundesliga", "Alemania"),
    "SPL": ("ksa.1", "Saudi Pro League", "Arabia Saudita"),
}
LEAGUES={**CORE_LEAGUES,**{k:v[0] for k,v in EXTENDED_COMPETITIONS.items()}}
