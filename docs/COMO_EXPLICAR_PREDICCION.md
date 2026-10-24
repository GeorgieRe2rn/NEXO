# Cómo explicar VELAR en clase

## Explicación oral

«Mi proyecto aplica Extracción de Conocimiento en Bases de Datos al fútbol. Recopila datos reales, limpia e identifica encuentros y equipos, transforma los últimos cinco partidos de cada equipo en indicadores y calcula probabilidades. Durante el encuentro incorpora el marcador, el minuto y las estadísticas disponibles. Guarda cada pronóstico antes de conocer el resultado, lo compara con datos finales y mide su error. Con suficientes resultados intenta calibrar sus estimaciones y conserva una nueva versión solamente si mejora en una validación temporal.»

## 1. Datos y preparación: selección, limpieza y transformación

El servidor consulta información pública de ESPN aproximadamente cada minuto; la interfaz consulta el servidor cada 15 segundos. Es sondeo periódico gratuito, sujeto a retrasos o fallas del proveedor. No es una transmisión instantánea garantizada.

Se identifican equipos, ligas y partidos, se almacenan fechas UTC y se muestran horarios de Hermosillo. Se necesitan cinco encuentros finalizados de la misma liga, anteriores al partido objetivo, por equipo. Se calculan puntos, medias de goles anotados y recibidos, tiros, tiros a puerta, posesión y otros indicadores disponibles. Un dato ausente no se convierte en un cero observado. Cuando se estima xG mediante tiros y goles se identifica como una aproximación, no como xG oficial.

## 2. Minería: pronóstico previo

Los indicadores generan una intensidad de goles esperados para cada equipo, llamada lambda (λ). La distribución de Poisson calcula la probabilidad de marcar k goles:

`P(X = k) = exp(-λ) × λ^k / k!`

Ejemplo exclusivamente didáctico: si λ = 1.5, la probabilidad de marcar exactamente dos goles es aproximadamente 25.1 %. No significa que obligatoriamente marcará dos.

La malla de marcadores local/visitante permite sumar los casos de victoria local, empate y victoria visitante. El motor previo aplica una corrección Dixon–Coles a marcadores bajos y mezcla 58 % de esta salida con 42 % de una función softmax basada en diferencias de forma reciente. Sus pesos iniciales son manuales: no debe afirmarse que esos coeficientes fueron aprendidos de una gran base histórica.

El módulo de mercados calcula goles totales con Poisson. Córners y amarillas usan hasta 40 partidos previos de la liga con contadores finales observados, suavizados hacia valores iniciales de dominio (9 córners y 4 amarillas, con peso de cinco partidos). Si no hay histórico suficiente, lo indica expresamente. Estos valores son supuestos iniciales, no estadísticas verificadas de la liga.

Las líneas de totales terminan en .5: «más de 2.5 goles» significa tres o más; «menos» significa dos o menos. La línea puede cambiar entre actualizaciones, pero cada selección conserva su propia línea y probabilidad.

## 3. Pronóstico en vivo

El previo queda guardado. El cálculo en vivo estima eventos adicionales usando marcador, tiempo transcurrido y las intensidades previas. Los tiros a puerta ajustan de forma acotada la intensidad de goles cuando están disponibles; córners y amarillas incorporan sus respectivos contadores.

Después suma los eventos ya observados a los posibles eventos restantes. Por ejemplo, un 1–0 al minuto 80 se evalúa como una ventaja existente con poco tiempo restante. No equivale a volver a simular el partido desde 0–0.

El horizonte de 95 minutos es una aproximación y las intensidades son heurísticas. Si faltan ambos contadores recientes, ese mercado en vivo no se habilita. Las selecciones se evalúan al final de los 90 minutos más añadido; prórroga o penales anulan la selección.

## 4. Registro automático y evaluación

El sistema registra automáticamente cuatro selecciones previas por cuenta y partido: local/empate/visitante, goles, córners y amarillas. Es una simulación sin dinero. Se usa el primer pronóstico previo válido disponible desde que se habilitó esta función. Para los totales se elige una línea cercana al total esperado dentro de los rangos configurados y se selecciona más/menos según la probabilidad mayor. No busca líneas triviales solo para aumentar los aciertos.

Se conservan usuario, partido, línea, elección, probabilidad, hora y versión. Una restricción única impide repetir el mismo partido y mercado en la misma cuenta. Las siguientes sincronizaciones y los pronósticos en vivo no modifican la elección congelada. Los partidos ya iniciados solo se incorporan con la marca de registro retrospectivo, como se explica al final.

El cierre utiliza los resultados finales reales confirmados. Si faltan tarjetas o córners finales, ese mercado permanece pendiente. Las correcciones del proveedor quedan auditadas. El panel agrupa por partido los cuatro mercados y muestra probabilidad previa, elección, resultado real y estado. La tasa de acierto excluye pendientes y anuladas; también se mide por mercado.

## 5. Aprendizaje supervisado y validación

El sistema acumula pronósticos prospectivos y resultados reales. Usa un ejemplo por partido y fase para que cientos de actualizaciones del mismo encuentro no aparenten cientos de partidos independientes.

A partir de 40 partidos distintos evaluados intenta ajustar temperatura de probabilidades 1X2 y multiplicadores de intensidades de goles, córners y amarillas. No reentrena los pesos originales del motor previo. Divide los partidos cronológicamente, aproximadamente 70 % para ajustar y 30 % para validar, con al menos 25 de entrenamiento y 10 de validación. Los partidos simultáneos permanecen en el mismo bloque; nunca divide fases del mismo partido entre ambos bloques. Cada fase y mercado también necesita evidencia suficiente.

Compara el candidato con la versión vigente en el mismo bloque posterior. Solo adopta el candidato si reduce el log loss medio en más de 0.002. Guarda la versión, cortes temporales y comparación; si no mejora conserva el modelo anterior. Esta validación permite seleccionar versiones, pero no sustituye una prueba externa independiente: reutilizar datos para decisiones sucesivas puede introducir optimismo.

Actualizar los datos en vivo y aprender son procesos distintos. No hay mejora garantizada ni precisión demostrada sin resultados suficientes. El panel muestra el número real de partidos evaluados.

## Métricas de la materia

- Accuracy: proporción de resultados 1X2 acertados.
- Precisión, recall y F1 por clase: cómo distingue local, empate y visitante.
- Matriz de confusión: qué clases confunde.
- Brier: error de las probabilidades, menor es mejor.
- Log loss: penaliza especialmente los errores con mucha confianza, menor es mejor. La calibración compara una media por partido de los mercados disponibles, cada uno contra su propia línea congelada.
- Calidad de datos: cobertura, vigencia, faltantes y validez de pronósticos previos.

Las métricas KDD del motor previo y el porcentaje de aciertos de selecciones personales son evaluaciones diferentes; no deben presentarse como la misma cifra.

## Separación del análisis y el registro

Con sesión iniciada se consultan el previo conservado y el pronóstico que evoluciona en vivo. El registro de apuestas automáticas tiene su propio apartado en el panel. No hay controles para apostar manualmente. Los registros manuales anteriores se conservan en la base, separados de las nuevas métricas automáticas.

Las líneas admitidas son goles 0.5 a 5.5, córners 6.5 a 11.5 y amarillas 1.5 a 6.5, en pasos de uno. Son rangos de este simulador, no cuotas oficiales. La automatización puede fallar en su predicción: un 100 % de confianza en el software no implica un 100 % de aciertos. La evidencia debe medirse con resultados futuros reales.

## Partidos ya en vivo: registros retrospectivos

Se pueden incorporar partidos en vivo usando exclusivamente un pronóstico previo archivado con fecha anterior al inicio. La fecha real de registro se conserva; no se antedata. Si solo existe el motor previo antiguo, resultado e intensidades de goles provienen de ese registro. Los mercados sin archivo se identifican como reconstruidos: goles desde intensidades previas y córners/amarillas desde supuestos iniciales de dominio, sin incorporar el marcador, minuto ni contadores actuales.

Los registros retrospectivos se evalúan con los resultados finales, pero tienen una tasa de acierto separada. No entran al aprendizaje ni a la tasa prospectiva. Si no existe ningún previo verificable anterior al inicio, no se inventa uno.

## Diagnóstico y doble oportunidad

La regla `doble-oportunidad-v1-5pp` recomienda 1X (local o empate) o X2 (visitante o empate) cuando equipo y empate son las dos clases de mayor probabilidad y su diferencia es como máximo 5 puntos porcentuales. Si ambas primeras opciones son equipos, no aplica. La probabilidad de la doble oportunidad se obtiene sumando los eventos mutuamente excluyentes; no se normalizan seis alternativas como si fueran clases independientes. Ejemplo: 0.40 local + 0.38 empate = 0.78 para 1X.

El umbral es una regla explícita solicitada para cubrir resultados cercanos, no un parámetro aprendido ni una promesa de rentabilidad. Las futuras selecciones guardan la versión de esta política y su motivo. Las anteriores no se reescriben: si la regla actual recomendaría otra cobertura, el panel la muestra como sugerencia distinta al registro original.

El diagnóstico privado separa resultados prospectivos y retrospectivos, comprueba la liquidación contra la fuente actual y muestra errores por mercado. La comparación de selección simple y doble oportunidad sobre partidos ya conocidos es un análisis retrospectivo, no evidencia independiente de mejor predicción. Cubrir dos resultados facilita acertar; no demuestra probabilidades más precisas ni ganancias, y el simulador no tiene cuotas ni dinero. Los coeficientes estadísticos siguen requiriendo calibración y validación temporal con datos suficientes.

## Revisiones automáticas previas al inicio

Esta actualización permite revisar las cuatro selecciones automáticas de partidos aún no iniciados cuando se adopta otra versión del modelo o cambia la política de selección. Cada revisión guarda la elección, línea, probabilidad, instantánea y versión anteriores y nuevas, con fecha y motivo. No basta el paso del tiempo ni se adoptan candidatos rechazados. Durante o después del partido el registro permanece cerrado. Esto reemplaza la regla anterior de congelar la primera selección desde su registro.

## Cartelera especial

El apartado Cartelera de partidos (/cartelera) consulta el calendario global de fútbol de ESPN y los calendarios NBA/NFL/MLB/NHL. Los filtros de fecha se calculan en Hermosillo, consultando ambos días UTC que cubren el día local. Es independiente de las cinco ligas del modelo: un evento del calendario no crea un pronóstico si faltan antecedentes. La oferta de Draftea está sin verificar; su web oficial pública consultada no expone su cartelera. No se atribuyen a Draftea eventos de ESPN ni se simulan cuotas oficiales.

## Referencia aportada de Draftea

Las siete capturas del usuario muestran 41 selecciones para el 15/10/2026. Se transcriben selección y momio americano y se cruzan con identificadores de ESPN mediante nombre, rival y hora. Esto acredita una referencia de las capturas, no una integración en vivo con la casa. Los favoritos destacados se ordenan según la probabilidad implícita del precio: para momios negativos, |momio|/(|momio|+100); para positivos, 100/(momio+100).

La probabilidad implícita incluye el margen de la casa y no es una predicción calibrada. Al faltar precios de los demás resultados no se puede eliminar el margen ni afirmar valor esperado positivo. Priorizar favoritos no demuestra que sean apuestas seguras. No se envían apuestas ni se forma una combinada real. Tampoco se reproducen las promociones o reglas de pago anticipado de Draftea.
