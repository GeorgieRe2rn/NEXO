# Arquitectura de pronósticos specialists-v2.0

Cuatro objetivos (1X2, goles, córners y amarillas) por dos fases (previo y en vivo). CatBoostClassifier MultiClass para 1X2; CatBoostRegressor Poisson para conteos. Cada uno compite por separado con una base Poisson de datos publicados. No se aplica regresión lineal a probabilidades.

## Datos y validación

- Exclusivamente partidos ESPN con identificador, marcador final y verificación. No se leen xG ni valores imputados de MatchStat.
- Identidad por ESPN ID entre competiciones; eventos deduplicados. Cinco antecedentes por equipo, máximo 365 días y anteriores al inicio por más de tres horas. El alcance es entre competiciones y no incorpora árbitros, lesiones ni alineaciones como variables.
- Las cifras faltantes no se convierten en cero. Cero explícito publicado sí es una observación válida. Para conteos se necesita historial real suficiente de ambos equipos.
- El entrenamiento previo reconstruye ejemplos históricos; no se confunde con evaluación prospectiva. En vivo solo aprende de capturas v2 guardadas antes del resultado; un partido aporta como máximo un ejemplo por fase y mercado.
- Mínimo operativo: 200 ejemplos utilizables. Corte cronológico aproximadamente 60/20/20, conservando partidos simultáneos y separando límites al menos tres horas. No es una garantía estadística de suficiencia.
- Entrenamiento CatBoost: 160 árboles, profundidad 4, regularización L2 8, semilla 42 y CPU limitada a dos hilos. El peso de ensamble {0,.25,.5,.75,1} se elige solo en validación. Prueba posterior independiente decide adopción frente a base y campeón con margen mínimo de .002 en log loss. La prueba no ajusta pesos. Nuevos intentos necesitan un bloque de prueba completamente posterior al último usado para decidir, incluso si ese intento fue rechazado.
- Métricas 1X2: log loss, Brier y accuracy. Conteos: NLL Poisson y MAE. La evaluación histórica es interna, no validación externa ni garantía futura.
- Los conteos siguen una distribución Poisson; la binomial negativa todavía no forma parte de esta versión. No se afirma que CatBoost sea mejor hasta observar una prueba válida.

## Versiones y migración

MarketLearner guarda mercado, fase, esquema, huella del dataset, reporte y modelo JSON (sin pickle). Solo se carga un candidato adoptado del mismo mercado/fase/esquema. Su despliegue se identifica con la combinación de revisiones activas.

ForecastRevision inicia una calibración neutral para la nueva arquitectura y para cada nuevo despliegue. No borra revisiones antiguas. Solo ejemplos prospectivos de la misma arquitectura/despliegue calibran sus probabilidades, con mínimo 40 partidos y partición temporal. Cada parámetro pasa un control de mejora de su propio mercado/fase; una mejora en goles no puede justificar empeorar tarjetas.

Las apuestas futuras reciben una revisión auditada; las que carecen de evidencia v2 quedan anuladas con motivo y pueden recuperarse antes del inicio al obtener evidencia. Las apuestas comenzadas/finalizadas no se reescriben. RETRO queda fuera del entrenamiento. Las predicciones antiguas permanecen identificadas por su versión.

Prediction es una proyección de compatibilidad de los mercados v2 para pantallas existentes; no un segundo motor. El cálculo legado deja de ejecutarse por defecto. Se mantiene FORECAST_ARCHITECTURE=legacy-v1 como opción de reversión técnica, excluyendo v2 del aprendizaje legado. El valor normal es specialists-v2.0.

## Ejecución

El entrenamiento se revisa al iniciar y cada seis horas, con el mismo bloqueo de escritura del feed para evitar carreras. Los pronósticos continúan con la base observada si falta evidencia. La interfaz de aprendizaje muestra los ocho estados, tamaños y métricas. Las plantillas no se usan como entrenamiento por el simple hecho de haberse importado.

Se creó una copia SQLite en backend/data/backups antes de migrar. Los datos y modelos locales están dentro de rutas excluidas de Git. No se modifican claves ni cuentas.

## Recuperación histórica y CatBoost experimental

Se añadió `training_history.audit_history`: comprueba los encuentros que ya tienen evaluación en el sitio, deduplica por partido y distingue falta de contador final de falta de antecedentes. No confunde número de selecciones con número de ejemplos. La pantalla Datos de entrenamiento muestra el diagnóstico por partido/mercado.

`recover_history` recupera calendarios de la temporada anterior de los equipos procesados, con un presupuesto acotado, caché de siete días y cuatro consultas simultáneas. Solo importa eventos finalizados, con liga/fecha/ID válidos y dentro del intervalo permitido. Nunca sobrescribe un partido existente. Los nuevos antecedentes se marcan como históricos para entrenamiento y no se agregan como apuestas retroactivas ni como partidos de la jornada. Los clubes de temporadas anteriores no se muestran como miembros actuales: se respeta el directorio vigente del proveedor.

Cada candidato entrenado, incluso si no fue adoptado, puede generar pronósticos CatBoost puros en sombra. ShadowForecast conserva modelo, fase, mercado, captura de origen, predicción, base y hora; tiene una restricción única por partido/modelo/fase. Se registra antes del inicio para PRE, o desde una captura contemporánea para LIVE; jamás se reconstruye un previo después del inicio. Se evalúa únicamente con finales confirmados. No crea ni modifica apuestas automáticas. Sus métricas prospectivas se muestran separadas de la prueba histórica y de producción.

Los modelos en vivo siguen necesitando capturas reales: los calendarios históricos no permiten inventar qué se sabía en un minuto concreto. Las mejoras históricas no garantizan mejora futura.
