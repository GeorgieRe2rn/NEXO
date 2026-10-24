# Momios y PWA

## Fuente y configuración
The Odds API v4. ODDS_API_KEY vive únicamente en .env (ignorado por Git); no se publica en el frontend.
Mercados consultados: h2h (90 minutos, tres resultados) y totals. Una región EU, siete ligas autorizadas, caché por liga de 24 horas. Hasta 14 créditos/día, aproximadamente 420 en 30 días si hay partidos en todas las ligas. No es un feed de cuotas en vivo. Una clave compartida con otros clientes puede agotar antes su cuota.

Las coincidencias exigen local/visitante en el mismo orden, nombres normalizados exactos y hora con tolerancia máxima de diez minutos. No hay fuzzy matching. Si falta una coincidencia, una casa, una línea o una cuota, se omite. Las cuotas no pertenecen a Draftea salvo que el proveedor lo identificara explícitamente; actualmente no hay cobertura de Draftea confirmada.

Cada captura es inmutable y conserva proveedor, casa, mercado, cuota decimal, hora de actualización y captura. Solo se importan partidos programados antes del inicio. Se descartan cuotas con fecha futura, más de 24 horas, precios inválidos o resultados incompletos. No se solicitan córners ni tarjetas sin cobertura confirmada.

## Combinación con el modelo
Por casa se calcula 1/cuota y se normaliza para quitar proporcionalmente el margen. Se promedian las probabilidades sin margen de las casas. Para goles se infiere una tasa Poisson desde la probabilidad más/menos y la línea: esa tasa es una estimación, nunca un conteo real.

Se conserva en cada nuevo pronóstico previo la predicción deportiva sin cuotas y la referencia del mercado. El combinador usa solo ejemplos prospectivos confirmados, uno por partido, del mismo despliegue deportivo. Mínimo 200 ejemplos; separación temporal 60/20/20 con huecos de tres horas. Los pesos 0, .25, .5, .75 y 1 se eligen en validación; un bloque de prueba posterior acepta una mejora de log loss de al menos .002 frente a la base y al combinador vigente. No reutiliza el mismo bloque de prueba para una nueva adopción. Los resultados 1X2 y goles se evalúan por separado.

La política vigente stable-market-v1 añade un peso inicial experimental cuando existe concordancia suficiente; si una evaluación posterior no demuestra mejora, el peso aprendido puede quedar en cero. Sin fuentes vigentes suficientes, peso cero. Al cambiar el despliegue deportivo se invalida el peso anterior. Las capturas viejas/ausentes nunca fuerzan una combinación. El ensemble adoptado lleva una identificación propia de revisión y usa parámetros de distribución neutros: no hereda la calibración deportiva anterior, ni entra en sus ejemplos de calibración. Las selecciones automáticas futuras se revisan con auditoría cuando cambia esa revisión; las comenzadas se conservan. En vivo mantiene sus especialistas separados; no se aplican cuotas previas como si fueran cuotas en vivo.

La revisión ocurre cada seis horas con el entrenamiento; la ingesta diaria y al iniciar el backend. GET /api/v1/odds/status y POST /api/v1/odds/sync requieren administrador (POST con CSRF). GET /api/v1/matches/{id}/odds muestra solo datos públicos. El panel de aprendizaje explica estado, peso, cobertura y capturas.

## PWA
Compilar: `cd frontend; npm run build`.
Arranque local de producción (ambos procesos apagados): `./run.ps1 -Production`.
El arranque habitual sirve la PWA compilada; usa ./run.ps1 -Dev para Vite de desarrollo. Si los puertos ya están ocupados, run.ps1 conserva esos procesos.

El manifiesto declara standalone, iconos 192/512, máscara segura, icono Apple y accesos directos. Workbox precachea únicamente la aplicación estática; nunca API, credenciales, momios ni marcadores. Sin conexión se muestra un aviso; al recargar no se inventan resultados offline. Hay invitación de instalación en navegadores compatibles y aviso de nueva versión.

En Android: menú del navegador > Instalar aplicación. En iPhone: Safari > Compartir > Agregar a inicio. Para instalar desde un teléfono real se requiere publicar el build bajo HTTPS con el backend accesible en el mismo origen /api. HTTP localhost es excepción solo en la propia computadora; http://IP-local no habilita una PWA instalable en un teléfono. No se ha publicado un dominio HTTPS desde este proyecto.

## Explicación académica
La regresión lineal suma variables con coeficientes aprendidos: y=b0+b1*x1+... No hay regresión lineal entrenada en esta arquitectura. CatBoostRegressor no significa regresión lineal: es boosting de árboles, en este caso con pérdida Poisson para conteos. CatBoostClassifier usa MultiClass para local/empate/visitante. Los modelos se actualizan en lotes y solo se adoptan tras evaluación temporal. Ninguno garantiza aciertos ni rentabilidad.


## Cambio: referencia automática stable-market-v1
La selección manual de casa se reemplaza por consenso robusto por mercado. Se descartan fuentes con más de 24 horas, cuotas inválidas y valores alejados más de 8 puntos de la mediana. Se requieren tres grupos de fuentes (las ediciones regionales conocidas y Betsson/Nordic no se cuentan por separado). No se garantiza independencia estadística entre operadores. Goles compara solo una misma línea: la más cubierta. Se exige dispersión máxima de 8 puntos tras filtrar.

Una captura solo permite medir concordancia transversal: peso inicial experimental 10%. Dos o más capturas separadas al menos 30 minutos y dentro de 48 horas permiten medir movimiento: si no excede 4 puntos, peso inicial 20%; si lo excede, aporte suspendido. La casa más próxima al consenso se muestra como referencia representativa, sin privilegiar marcas ni pagos altos. Se usa el consenso, no esa única casa.

Estos pesos iniciales son reglas de diseño, no parámetros aprendidos ni mejora validada. Reemplazan la espera con peso cero de la versión anterior, a petición del usuario. Al reunir ejemplos prospectivos de la política nueva, la validación temporal puede reemplazarlos por un peso aprendido, incluido cero. No se mezclan ejemplos de la política antigua. Los cambios solo revisan apuestas simuladas futuras, preservando versiones y apuestas ya iniciadas. No se aplican cuotas previas al motor en vivo ni a mercados de córners/tarjetas sin cobertura.
