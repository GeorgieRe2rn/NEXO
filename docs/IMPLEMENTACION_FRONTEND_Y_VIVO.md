# Implementación del rediseño y seguimiento

Fecha de revisión: 14 de octubre de 2026, America/Hermosillo.

## Cambios implementados

Se reemplazó la estructura visual por un sistema grafito, blanco y lima, con navegación de escritorio,
barra inferior móvil y páginas de jornada, seguimiento, plantillas, equipo, análisis y administración.
Los títulos no llevan los números de presentación de los mockups.

El centro de partido permite consultar resumen, estadísticas, plantillas y análisis previo. Las plantillas
se identifican como tales y no se presentan como alineaciones confirmadas. La comparación de equipos
usa resultados recientes y permite seleccionar al rival. Las ausencias se representan con una raya.

Los datos se actualizan mediante polling compartido del backend (aproximadamente 60 s) y consulta de la
interfaz a la base (15 s). La pestaña oculta pausa sus consultas. Se muestran reconexión, última consulta,
estado por competición y advertencia de fuente demorada. Los cambios de marcador producen un aviso
visual. Córners, tarjetas y tiros se actualizan en el detalle cuando el proveedor publica nuevos valores.

## Integridad del calendario

`live_feed.py` consulta ESPN público para Liga MX, Premier League, La Liga, Serie A y MLS.
Cada encuentro conserva `provider`, `provider_id`, `verified_at`, hora UTC y un resumen con eventos,
estadísticas y vínculo a la fuente. Los identificadores de ESPN no colisionan con las integraciones
anteriores. El feed público excluye datos anteriores sin verificación y encuentros de demostración.

Las fechas no se cambian para hacer aparecer partidos futuros. Los estados cancelado, pospuesto,
suspendido y retrasado se preservan. Un programado que vence no se transforma por inferencia en vivo.
Si un reporte en vivo supera tres minutos sin confirmación se retira su etiqueta de actualidad.
Si falla la conexión de la interfaz, también se retira esa etiqueta hasta recuperar datos.

La primera consulta completa recuperó 85 encuentros del calendario y posteriormente se integraron
resultados anteriores para formar ventanas. Estos conteos cambian con el avance de la jornada.
Se consultaron 108 plantillas y se actualizaron 3355 jugadores de las temporadas reportadas por la fuente.
No se reutilizan las plantillas de demostración como plantilla actual.

Se contrastaron 31 encuentros europeos contra football-data.org: 10 de Premier League, 11 de La Liga
y 10 de Serie A. Los 31 coincidieron en equipos y hora de inicio UTC. Dos coincidencias requirieron
normalizar nombres equivalentes (Racing Santander y Como 1907). El archivo
`VERIFICACION_CALENDARIO.json` conserva las fechas y resultados de esa comprobación sin credenciales.
Liga MX y MLS se consultaron directamente en ESPN; no se verificaron todos sus partidos contra una
segunda fuente independiente. No se afirma una verificación independiente de todas las estadísticas.

## Persistencia y modelo

El nuevo seguimiento no llama a las limpiezas que eliminaban partidos y pronósticos. El GET de partidos
tampoco borra datos. Se preservan los cálculos previos cuando el partido comienza. Los encuentros en vivo
sin predicción previa muestran ese estado y no generan una retrospectiva presentada como pronóstico.
Solo cinco partidos verificados de cada equipo habilitan el cálculo. Los partidos de otra competición
que aparezcan entre los últimos cinco del proveedor se excluyen. Si esa mezcla deja una ventana incompleta, se consulta el calendario de resultados del equipo, filtrado por la misma liga, sin incorporar partidos futuros.

Se retiró el recorte artificial del Over 2.5 y se versionó el motor como `forma-l5-v1.1`.
Los booleanos de las migraciones usan TRUE/FALSE para compatibilidad PostgreSQL. Antes de migrar la
SQLite existente se creó una copia local en `backend/data/forma-before-redesign.db`.

## Límites de la fuente gratuita

El endpoint público de ESPN no tiene SLA contratado. La interfaz es automática, pero no puede prometer
la latencia de una plataforma de apuestas. Los eventos y el marcador pueden publicarse en momentos
diferentes: se informa cuando un evento de gol todavía no está reflejado en el marcador recibido.
No se deduce un marcador del texto de comentarios ni se simulan eventos.

El plan gratuito configurado de API-Football respondió que solo permite temporadas de 2022 a 2024;
por eso no se usa como fuente de 2026. football-data.org gratuito demora los marcadores y no cubre
los córners solicitados sin un complemento. El seguimiento implementado no contrata servicios ni usa
claves de pago. Los proveedores pueden cambiar cobertura, disponibilidad o condiciones de acceso.

Los xG de marcadores históricos sin detalle son estimados. Los pesos logísticos siguen siendo manuales
y la confianza no está calibrada; entrenar y validar cronológicamente requiere una fase posterior.
Las métricas de evaluación requieren esperar resultados de partidos que tengan pronóstico previo válido.

## Validación

- 24 pruebas backend: motor, calendario, métricas, API, deduplicación de eventos, actualización de goles
  y córners, conservación del pronóstico, estados excepcionales, exclusión de datos sin verificar y
  ausencia de pronósticos con ventanas incompletas.
- 3 pruebas frontend: cambio de día UTC/Hermosillo, horario contrastado y probabilidades ausentes.
- Compilación de producción con carga de páginas por separado y sin la advertencia anterior de 500 kB.
- Inicio de sesión real y endpoint de métricas comprobados con el administrador local, sin cambiar credenciales.
- Revisión de navegación, datos visibles y distribución en navegador a tamaños de escritorio y móvil.

La API se probó con SQLite. No se ejecutó una migración ni pruebas de concurrencia en PostgreSQL.
Los bloqueos de ingesta compartidos son por proceso: el arranque local usa un solo worker.
