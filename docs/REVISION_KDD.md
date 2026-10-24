# Revisión técnica y métricas de extracción de conocimiento

## Qué hace el proyecto

Velar / FORMA consulta proveedores de fútbol, transforma sus respuestas a tablas
relacionales, materializa ventanas de cinco partidos y genera probabilidades 1X2
y Over/Under 2.5. Usa FastAPI, SQLAlchemy, PostgreSQL con fallback SQLite, React
y un motor Poisson/Dixon-Coles combinado con una función softmax de pesos manuales.

Ya existe una base del proceso KDD: selección, limpieza, transformación y generación
de conocimiento. Faltaba medir la calidad de ese conocimiento con resultados reales.

## Hallazgos por prioridad

| Prioridad | Evidencia | Consecuencia y corrección pendiente |
| --- | --- | --- |
| Alta | `backend/app/etl/hybrid.py`, `_purge_league_matches`, invocada en las ingestas de ligas | Borra partidos, estadísticas y pronósticos antes de recargar. Se pierde el histórico para evaluar. Sustituir el borrado por upserts con identidad de proveedor y conservar pronósticos previos al inicio. |
| Alta | `backend/app/etl/fixtures.py`, `purge_invalid_jornada`; `backend/app/api/v1/router.py`, `matches` | Un GET de partidos puede borrar programados vencidos y sus pronósticos antes de recibir el marcador final. Separar visibilidad de eliminación; reconciliar resultados en el ETL. |
| Alta | `backend/app/ml/engine.py`, `_PRIOR_COEF`, `fit_logistic`; `backend/app/services/knowledge.py`, `predict_match` | El flujo usa pesos manuales; no llama al entrenamiento disponible. No hay evidencia para afirmar que sea una regresión entrenada o calibrada. Construir ventanas históricas etiquetadas y validar por fecha antes de desplegar coeficientes aprendidos. |
| Alta | `backend/app/etl/transform.py`, `_stat_map`, `parse_team_stats`; `backend/app/etl/hybrid.py`, `_stats_from_official_score` | Ausencias pasan a 0, posesión a 50 y xG a un proxy; se confunden observaciones con imputaciones. Añadir origen, indicador de imputación y valores nulos para medir completitud real. |
| Alta | `backend/app/core/config.py`, valor predeterminado de `app_secret`; `backend/app/core/security.py`, `_serializer` | Si no se configura un secreto distinto, las cookies se firman con un valor conocido. Rechazar secretos predeterminados al arrancar en producción. No se inspeccionaron ni publicaron valores de `.env`. |
| Media | `backend/app/infrastructure/db/session.py`, `migrate_schema` | Los literales `BOOLEAN DEFAULT 0/1` y `SET is_active = 1` son incompatibles con booleanos PostgreSQL cuando se ejecutan esas migraciones sobre tablas antiguas. Usar `FALSE/TRUE` y migraciones versionadas. No se reprodujo contra un servidor PostgreSQL. |
| Media | `backend/app/ml/engine.py`, `poisson_grid` | Over 2.5 se limita artificialmente al intervalo 0.18–0.92; el valor ya no representa exactamente la suma de probabilidades de la malla anunciada. Eliminar el recorte o documentar y validar la transformación. |
| Media | `backend/app/ml/form.py`, `compute_team_form`; `backend/app/ml/engine.py`, `_confidence` | Un solo partido obtiene consistencia 1; la confianza mezcla estabilidad y tamaño de muestra sin validación de calibración. No interpretar este indicador como porcentaje de acierto. |
| Media | `frontend/src/App.jsx` | `Pipeline.jsx` y `Methodology.jsx` existen pero no están conectados a rutas. Integrarlos si se usarán en la exposición académica. Las nuevas métricas sí están conectadas al panel. |
| Baja | `README.md`, `Methodology.jsx`, `ml/form.py` y `services/knowledge.py` | La documentación simplifica fórmulas de xG y jugador clave y anuncia `/docs`, mientras la API configura `/api/docs`. Actualizar para que la explicación coincida con el cálculo real. |

`error.txt` contiene rechazos de conexión hacia `127.0.0.1:8000`: evidencia de que el
backend no respondía al proxy en ese momento, no prueba de un fallo actual del modelo.

## Métricas implementadas

Acceso: **Administración → Métricas KDD**. API: `GET /api/v1/metrics`, protegida
por la sesión de administrador. Se calcula en lectura, sin llamadas a proveedores,
entrenamiento ni modificaciones a las tablas existentes.

| Métrica | Definición / interpretación |
| --- | --- |
| Accuracy | Aciertos / casos evaluados. Puede ocultar el mal desempeño en empates. |
| Precisión por clase | TP / (TP + FP). De los pronósticos de esa clase, cuántos acertaron. |
| Recall por clase | TP / (TP + FN). De los resultados de esa clase, cuántos se detectaron. |
| F1 por clase y macro | F1 = 2PR/(P+R); macro promedia las tres clases con igual peso. Denominadores nulos producen 0; se muestra el soporte para advertir clases ausentes. |
| Matriz de confusión | Filas reales, columnas predichas; orden LOCAL, EMPATE, VISITANTE. |
| Log loss | Media de −ln(probabilidad del resultado real); menor es mejor. Se usa suelo numérico 1e−15. |
| Brier multiclase | Media de Σ(p_k − y_k)², sin dividir por clases, rango 0–2; menor es mejor. |
| Referencia uniforme | Probabilidades 1/3 por clase: log loss ln(3) y Brier 2/3. No es un modelo entrenado ni demuestra superioridad estadística. |
| Cobertura evaluable | Pronósticos válidos evaluados / partidos oficiales finalizados almacenados, excluyendo H2H exclusivo. |
| Completitud de marcador | Finalizados con ambos goles no negativos / finalizados del mismo universo. |
| Ventanas completas | Snapshots con cinco partidos / snapshots almacenados. No mide completitud de campos. |
| Duplicados candidatos | Grupos de partidos con mismo ID externo. Requieren revisar proveedor; el esquema actual no identifica ese origen. |

Se excluyen pronósticos calculados al inicio o después, marcadores ausentes o negativos
y probabilidades no finitas, fuera de rango o cuya suma se aleje de 1 más de 0.001.
Las pequeñas diferencias por redondeo se normalizan. El resultado se obtiene del marcador,
y la clase predicha del máximo de probabilidades; en empates se elige la primera clase del orden indicado.

Sin casos, las métricas agregadas son `null` y la interfaz muestra **Sin evidencia**.
En la inspección de `backend/data/forma.db` realizada durante esta revisión se
encontraron 151 partidos finalizados, 30 programados y 60 predicciones, pero ninguna
predicción asociada a un partido finalizado. Es una lectura de la SQLite local;
no describe necesariamente una instancia PostgreSQL configurada por separado.
Menos de 30 casos muestra **muestra pequeña**; 30 no constituye garantía estadística.
Se listan versiones del motor y motivos de exclusión. Esta evaluación es descriptiva
sobre registros existentes: no reemplaza un backtest temporal ni mide por sí sola
la calibración, y solo verifica la fecha guardada del pronóstico.

## Próximos pasos para una entrega académica más completa

1. Conservar pronósticos y snapshots inmutables anteriores al encuentro y actualizar
   los marcadores oficiales, sin borrar el histórico. No reconstruir predicciones
   pasadas con información que llegó después.
2. Registrar procedencia e imputación de cada estadística y separar datasets reales
   de demostración. Así se podrán calcular tasas de faltantes, imputación y validez.
3. Construir ejemplos históricos con las cinco observaciones estrictamente anteriores
   a cada partido. Usar muchos partidos como ejemplos conserva la restricción last-5
   de cada vector de entrada.
4. Separar entrenamiento, validación y prueba cronológicamente; ajustar pesos solo
   con entrenamiento y comparar contra una referencia ajustada únicamente con ese conjunto.
5. Añadir calibración por intervalos y resultados por liga y versión cuando exista
   suficiente soporte. Para ampliar minería de datos: clustering de estilos de equipos
   con silhouette y reglas de asociación con soporte, confianza y lift; son extensiones
   propuestas, no funciones implementadas en esta revisión.

## Verificación

- Suite backend: 15 pruebas aprobadas, incluidas cuatro nuevas sobre métricas.
- Se comprueban valores conocidos, ausencia de evidencia, probabilidades erróneas,
  matriz de confusión y exclusión temporal con SQLite en memoria.
- Build frontend completado; Vite advierte un bundle JavaScript superior a 500 kB.
- No se ejecutó una ingesta externa, una prueba visual de navegador ni una migración
  contra PostgreSQL. No se modificaron secretos ni datos locales para la evaluación.
