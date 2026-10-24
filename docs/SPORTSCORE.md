# Cancha SportScore

El inicio y la sección En vivo (Dashboard compartido) incluyen el preset oficial gratuito:

https://sportscore.com/embed/tracker/football/live/?theme=light

Este preset elige un partido de la cobertura del proveedor automáticamente. No corresponde necesariamente al destacado de Nexo, ni cambia con los filtros de liga o fecha. Se presenta en una sección independiente con esta indicación; no se inserta en el detalle de otro encuentro ni se usa su marcador para liquidar selecciones o entrenar modelos.

El iframe conserva toda la atribución interna y un enlace visible de atribución exterior. Es responsivo, se carga de forma diferida y tiene botones para recargar o abrir directamente. Un fallo interno del proveedor no siempre produce un evento `error` del iframe, por lo que los botones permanecen accesibles.

No requiere registro ni clave. El proveedor anuncia refresco del contenedor aproximadamente cada cinco minutos; la animación interior depende de su feed. No se garantiza que cada desplazamiento visual represente coordenadas físicas reales del balón. No se añaden ni interpolan datos de SportScore en Nexo.

La PWA no almacena este recurso externo para uso offline. Sin conexión no hay seguimiento en directo.

Condiciones consultadas el 23 de octubre de 2026: https://sportscore.com/embed/ . Uso gratuito editorial, blogs y sitios de aficionados con atribución visible. Para explotación comercial a gran escala, consultar al proveedor.

El adaptador opcional de Sportradar permanece sin activar; no se descarga su script sin configuración explícita.

Pilotos verificados: Al Faisaly–Al Nassr (23/10/2026 13:30 UTC) e Ipswich Town–Nottingham Forest (23/10/2026 19:00 UTC). Se carga el widget específico solo si coinciden liga, equipos, hora y estado LIVE, dentro de cuatro horas del inicio. No existe aún descubrimiento automático general; otros encuentros mantienen la cancha de Nexo identificada como tal. La fuente ESPN determina el estado del partido, aunque SportScore reporte otro estado.

Modo claro/oscuro: botón en cabecera pública y navegación administrativa, preferencia local nexo-theme y apariencia del sistema al primer acceso. SportScore recibe el parámetro theme correspondiente.

Actualización de alcance: se retiró el preset general que elegía un partido ajeno. Inicio y detalle usan LiveCoverage del encuentro real seleccionado: cancha externa solo para coincidencias verificadas y estadísticas ESPN al costado; sin cancha vinculada, cronología y estadísticas, nunca cancha ilustrativa. En móvil las columnas se apilan. No se atribuye disponibilidad general a los dos pilotos manuales.
