# Rastreador en vivo

Se preparó el adaptador de Sportradar `match.lmtPlus` en inicio y detalle de partidos en vivo. Sin configuración sigue la cancha ilustrativa de Nexo, con acciones confirmadas de ESPN, sin simular posiciones del balón.

## Activación pendiente de acceso del proveedor

1. Solicitar a Sportradar acceso autorizado al widget y el alias público de cliente. Deben autorizar también los dominios de uso (incluido localhost si procede) y las competiciones. La prueba de la API de datos no concede automáticamente licencia de widgets.
2. Copiar `frontend/.env.example` a `frontend/.env.local`. Completar el alias público y el mapa JSON de partidos. No poner claves privadas en variables `VITE_*`: se incluyen en el navegador.
3. El mapa relaciona ID interno de Nexo con ID numérico de Sportradar. Verificar equipos, fecha de inicio y competición. Los IDs de ESPN no son intercambiables con los del proveedor. Sin coincidencia explícita no se carga el widget.
4. Reconstruir el frontend con `npm run build` desde `frontend` y recargar la PWA (aceptar la actualización disponible).

Solo se descarga el script del proveedor cuando hay alias y coincidencia configurados. La instancia se retira al cambiar de página. Si falla la descarga o no se confirma el montaje en 15 segundos, vuelve a la visualización de ESPN. Errores de licencia que renderice el proveedor pueden aparecer dentro del propio widget; deben resolverse con él.

No se ha activado un servicio de pago ni usado credenciales de demostración. La visualización no modifica los modelos ni sus datos de entrenamiento.

Documentación oficial: https://developer.sportradar.com/widgets/docs/getting-started y https://apidocs.sportradar.com/resources/widgets/docs/lmt/lmt-plus
