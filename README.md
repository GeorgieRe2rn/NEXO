# VELAR · El partido, en contexto

Plataforma académica de análisis de fútbol para **Extracción de Conocimiento en Bases de Datos**.
Calendario real, seguimiento de encuentros y pronósticos basados en los últimos cinco partidos.

## Experiencia

- Jornada y centro en vivo, con filtros por competición, fecha y estado.
- Marcador, minuto reportado, goles, córners, tarjetas, cambios y estadísticas disponibles.
- Plantillas actuales, búsqueda de jugadores, forma reciente y comparación entre equipos.
- Panel de administración con estado de las fuentes y métricas KDD.
- Diseño adaptable a escritorio y móvil; horarios en **America/Hermosillo (UTC−7)**.

## Fuente y actualización

El seguimiento principal consulta el **endpoint público de ESPN**, sin clave ni plan de pago.
No es una API contratada: puede retrasarse, cambiar su estructura o dejar de responder.
La interfaz muestra fuente, hora de consulta, errores, datos pendientes y falta de evidencia.

- Backend: consulta compartida aproximadamente cada 60 segundos, con un solo escritor de ingesta.
- Interfaz: consulta la base cada 15 segundos; pausa consultas en pestañas ocultas y reintenta al volver.
- Calendario: consulta completa cada 3 horas; cubre los próximos días y conserva los registros anteriores.
- Plantillas: consulta de temporada actual, con caché de 24 horas.
- No se ruedan fechas de ejemplos ni se publican partidos antiguos sin verificar como jornada actual.
- Goles y córners solo cambian cuando llegan de la fuente. No se simula el reloj.
- Si el marcador aún no refleja un evento de gol, se muestra un aviso de confirmación pendiente.

API-Football y football-data.org permanecen en el repositorio como integraciones anteriores.
La clave gratuita de API-Football configurada rechazó la temporada 2026 en la verificación;
no se necesita para el nuevo seguimiento. football-data.org se usó para contrastar calendarios europeos.

## Stack

FastAPI · SQLAlchemy 2 · PostgreSQL/SQLite · React 19 · Vite · Tailwind · lucide-react.
El frontend consulta exclusivamente al backend. Los datos del seguimiento se identifican con proveedor,
ID de proveedor, fecha UTC de inicio y última consulta. El histórico no se elimina al refrescar.

## Ejecutar en Windows

```powershell
.un.ps1
```

Si las dependencias no existen, el script prepara el entorno. PostgreSQL es opcional para desarrollo;
si no está disponible, se usa `backend/data/forma.db`. Para PostgreSQL: `docker compose up db -d`.

- Sitio: http://127.0.0.1:5173
- Administración: http://127.0.0.1:5173/admin
- Documentación API: http://127.0.0.1:8000/api/docs

Las credenciales generadas se guardan localmente en `backend/data/admin_credentials.txt`.
La carpeta `data` está excluida de Git. No publiques ese archivo.
Configura un `APP_SECRET` propio antes de usar el proyecto en producción.

Arranque manual:

```powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000
# En otra terminal:
cd frontend
npm install
npm run dev
```

El scheduler está pensado para **un proceso de API**. No ejecutar varios workers sin trasladar
la exclusión de ingesta y la programación a un servicio compartido.

## Modelo y evaluación

Cada pronóstico requiere cinco encuentros finalizados y verificados de la misma competición por equipo,
anteriores al inicio. Las ventanas incompletas no generan probabilidades. Al pasar a en vivo se conserva
el pronóstico previo; no se reconstruyen pronósticos históricos con resultados ya conocidos.

Motor `forma-l5-v1.1`: malla Poisson/Dixon–Coles y softmax de pesos manuales, combinación 58/42.
Los xG ausentes son proxies y los datos de marcador sin estadísticas requieren imputación;
la metodología pública explica estas limitaciones. La confianza es heurística, no calibrada.

En **Administración → Métricas KDD**: accuracy, precisión, recall, F1 macro, matriz de confusión,
log loss, Brier, cobertura evaluable, completitud de marcadores y ventanas de cinco partidos.
Sin resultados válidos se muestra **Sin evidencia**, nunca una precisión inventada.

API pública: `GET /api/v1/feed`, `GET /api/v1/matches/{id}`, `GET /api/v1/teams/{id}`.
API protegida: `GET /api/v1/metrics`, `POST /api/v1/feed/refresh`, `POST /api/v1/etl/rosters`.

## Verificación

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest
cd ../frontend
npm test
npm run build
```

El reporte de contraste de 31 encuentros europeos está en `docs/VERIFICACION_CALENDARIO.json`.
Es una comprobación fechada; el calendario se sigue actualizando y puede cambiar después.
La implementación y sus límites se documentan en `docs/IMPLEMENTACION_FRONTEND_Y_VIVO.md`.
La revisión inicial, anterior al rediseño, se conserva en `docs/REVISION_KDD.md`.
