# Arquitectura FORMA

## Principio

El conocimiento no es la tabla de la temporada. El conocimiento es la **ventana de los últimos 5 partidos**, materializada en PostgreSQL y consumida por un modelo interpretable.

## Capas (Clean Architecture)

```
UI React  →  FastAPI (casos de uso)  →  dominio ML  →  infraestructura (SQL + APIs)
```

- `api/v1` — controladores, sin lógica de predicción.
- `services` — orquesta forma, jugador clave y serialización.
- `ml` — `compute_team_form` + `predict_match` (Poisson × logística).
- `etl` — extract/transform/load con rate-limit y `api_cache`.
- `infrastructure/providers` — API-Football (5 ligas) y football-data.org (fallback EU).
- `seed` — universo académico reproducible (`DATA_SOURCE=seed`).

## Tablas de conocimiento

| Tabla | Qué extrae |
| --- | --- |
| `match_stats` | Hechos por equipo y partido (goles, xG, tiros, posesión…) |
| `player_match_stats` | Hechos de jugador en esa misma ventana |
| `team_form_snapshots` | Agregado last-5 anclado a un partido futuro |
| `player_form_snapshots` | Ranking de forma; `is_key_player` |
| `predictions` | 1X2, O/U 2.5, λ, confianza, explicación |
| `api_cache` | JSON crudo + TTL para no quemar el cupo gratuito |

## Flujo de una predicción

1. Se toman los 5 `match_stats` más recientes del local y del visitante (`status=FINISHED`, `is_h2h_only=false`).
2. Se calculan GF/GA/xG/tiros/posesión/córners/tarjetas y los índices de ataque/defensa.
3. Poisson-Dixon-Coles genera la malla de marcadores 0–8.
4. La logística usa el vector de diferencias last-5.
5. Blend 58/42. Over 2.5 = P(goles ≥ 3). Confianza = hueco + muestra + estabilidad.
6. El H2H (últimos 3) es contexto visual; **no entra en el modelo**.

## APIs gratuitas y rate-limit

- API-Football: 100 req/día, 10/min. Cubre Liga MX y MLS.
- football-data.org: 10/min, ligas europeas, sin xG.
- Token bucket a 8 req/min + caché 12 h en `api_cache`.
- El frontend nunca llama a las APIs externas.
