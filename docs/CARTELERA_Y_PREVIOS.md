# Estado vigente — retirada de competiciones adicionales

Por solicitud del usuario se retiraron las ocho competiciones adicionales y sus encuentros, predicciones y registros asociados. Solo se conservan Liga MX, Premier League, La Liga, Serie A y MLS. Hay un respaldo anterior a la retirada en backend/data/forma-before-removing-extra-competitions.db.

No se utilizan los valores de relleno 9 córners / 4 amarillas. Estos mercados solo se pronostican si existen cinco partidos anteriores por cada equipo con ambos contadores reales finales publicados. Se utiliza la media de los totales observados, sin sustituir datos ausentes por ceros ni por una media inicial. Un cero publicado sí se conserva. Cuando no alcanza el historial, el mercado queda sin pronóstico ni apuesta nueva.

Los pronósticos anteriores de córners y amarillas que usaban valores iniciales o suavizado fueron retirados. Sus selecciones quedan anuladas y auditadas; no se muestran sus probabilidades ni se vuelven a liquidar. Se excluyen sus bases del entrenamiento. Las estadísticas reales disponibles del partido siguen mostrándose aunque no haya pronóstico.

Las probabilidades y goles esperados son estimaciones del modelo, no mediciones ni garantías. En las fichas de forma no se muestran xG proxy ni otras estadísticas imputadas como si fueran observaciones. La sincronización requiere que el backend permanezca encendido.


## Ampliación exclusiva de córners y amarillas — 16 de octubre de 2026

La importación ahora consulta resúmenes históricos de ESPN para los partidos previos de los equipos de las cinco ligas originales. Solo almacena córners y amarillas en la tabla independiente `count_observations`. Comprueba identificador, competición, local/visitante, fecha y final confirmado sin prórroga. No escribe marcadores, MatchStat ni Prediction. La carga inicial incorporó 277 resúmenes con los cuatro contadores publicados.

El modelo de estos dos mercados usa cinco antecedentes reales por equipo, anteriores al partido. Se muestra la cobertura local/visitante y cada antecedente con sus contadores y enlace a la fuente. Se eliminan duplicados si los equipos compartieron un enfrentamiento. Los ceros publicados se conservan; las ausencias quedan vacías. No hay medias iniciales 9/4 ni relleno. Los totales esperados y probabilidades siguen siendo estimaciones Poisson, no resultados garantizados.

Las selecciones de córners y amarillas previamente retiradas solo se recuperan antes del inicio cuando aparece historial suficiente. La recuperación conserva auditoría y registra una nueva fecha de creación; no atribuye el nuevo análisis a la fecha del registro retirado. No se recuperan selecciones durante el partido ni después del final. En la carga inicial quedaron disponibles ambos mercados en 118 próximos encuentros; se recuperaron 130 selecciones existentes y el resto se registró cuando antes no existía selección.

La carga inicial verificó mediante huellas que las selecciones de resultado y goles, las predicciones 1X2, MatchStat y Match permanecieran idénticos. El informe está en HISTORIAL_CORNERS_AMARILLAS.json. El seguimiento procesa hasta 24 resúmenes por sincronización, con cuatro consultas concurrentes, caché de 24 horas para observaciones históricas y reintento diferido ante fallos. La falta de estos datos no interrumpe los demás mercados.
