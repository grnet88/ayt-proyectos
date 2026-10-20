# Estado del proyecto

Última actualización: 2026-10-20.

## Qué se agregó en la v0.2 (etapa 0, cimientos)

- **Usuarios y roles:** superadministrador `aytroot` (fijo, no se puede borrar ni cambiar de rol, solo él
  cambia su contraseña), ingeniero, relevador, comercial y visor cliente. Editan superadministrador,
  ingeniero y relevador; comercial y visor solo miran. El visor ve solo los proyectos que se le asignan.
- **Configuración inicial:** la primera vez, desde la PC del servidor, se define la contraseña de aytroot
  (mínimo 8 caracteres, con botón Mostrar). Nunca está escrita en el código.
- **Llave de recuperación:** al configurar se descarga `aytroot-llave-recuperacion.key`. Se guarda solo su
  huella. Con el archivo, desde la PC del servidor ("¿Perdiste la contraseña?" en la pantalla de ingreso o
  `python -m app.recuperar ruta.key` en la carpeta backend) se define una contraseña nueva; al usarla se
  descarga una llave nueva y la anterior deja de valer. aytroot puede regenerarla desde "Usuarios y llave".
- **Escenarios:** cada proyecto tiene una o más opciones o etapas de obra (copiando la actual o vacías).
  Cada escenario tiene sus elementos, parámetros y cálculo; el listado CSV se exporta por escenario.
- **Plantas:** el modelo ya soporta varias plantas; por ahora solo se dibuja la planta Exterior (mapa).
- **Auditoría** de ingresos, cambios de usuarios, llaves y proyectos.
- Los proyectos de la v0.1 se migran solos a un escenario "Opción A".
- Límite de caída de tensión por defecto: 3 % (configurable).

Probado: 14 pruebas automáticas y recorrido completo en navegador (configuración, llave, ingreso,
distribución, duplicar escenario, usuario visor de solo lectura, recuperación y rechazo de la llave usada).

## Orientación de dispositivos (2026-10-20)

- Todo elemento puntual (cámara, gabinete, rack, UPS) tiene orientación: `properties.azimut`, grados enteros
  0-359 desde el norte en sentido horario. El ícono gira y una muesca amarilla marca el frente.
- Se edita con el control deslizante y el campo del panel, con los botones ±15°, con R / Shift+R, o
  arrastrando el punto amarillo que aparece alrededor del elemento seleccionado (el cono se ve girar en vivo).

## Qué funcionaba desde la v0.1 (etapa 1)

- Proyectos: crear, renombrar, cliente, categoría, borrar. Se guardan solos.
- Mapa satelital (Esri) y de calles (OSM), búsqueda por dirección o coordenadas, escala real.
- Dibujo de perímetro cerrado o abierto, con edición de vértices.
- Ubicación manual de cámaras, gabinetes, rack central y fuentes/UPS. Todo se puede arrastrar.
- Distribución automática sobre el perímetro: cámara en cada esquina mirando a lo largo del lado,
  espaciado según el alcance de analítica del modelo, gabinetes cada N cámaras.
- Cono de visión de cada cámara según ángulo horizontal y alcance; PTZ como círculo.
- Cálculos:
  - Cobertura analítica del perímetro y tramos ciegos marcados en rojo.
  - UTP por cámara (alerta si supera 90 m), switch PoE por gabinete según puertos y presupuesto PoE.
  - Fibra: ramales desde el rack central en ambos sentidos del cerco, con reservas.
  - Energía: cada gabinete se alimenta de la fuente más cercana; caída de tensión acumulada por
    ramal según sección, alerta si supera el límite, UPS sugerida por carga.
  - Ancho de banda total y almacenamiento para N días.
  - Listado de equipos y materiales, exportable a CSV.
- Catálogo: modelos base tomados de los datasheets de Cinco Lagos ABC y Cadaques; se pueden
  duplicar, editar y agregar modelos propios.

## Supuestos a validar con Gastón

- Alcance de analítica por defecto = distancia DORI de **observación** del datasheet
  (HDW3849 2.8 mm: 36,4 m). Se puede cambiar por modelo o por cámara.
- Zona ciega bajo la cámara: 2 m.
- Resistividad del cobre 0,0225 Ω·mm²/m (a temperatura de servicio), factor de potencia 0,9,
  eficiencia de fuentes 85 %, límite de caída 3 %.
- Reservas: 5 m de UTP por cámara, 20 m de fibra y 5 m de energía por gabinete, factor 1,05 de recorrido.
- Bitrate: 6 Mbps para 8 MP, 3 Mbps para 2 MP (H.265).

## Próximos pasos

Ver [ROADMAP.md](ROADMAP.md). Sigue la etapa 1 (exterior completo): altura, inclinación, PPM y zona
ciega por cámara, muros y obstáculos, canalizaciones y cámaras de paso, planos calibrados, KML/KMZ y DXF.

## Pendientes de infraestructura

- Repositorio GitHub: falta que Gastón conecte su cuenta y cree el repositorio; mientras tanto el
  código está en la carpeta compartida del proyecto (`ayt-proyectos/`) con su historial git.
