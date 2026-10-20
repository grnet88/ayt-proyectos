# Estado del proyecto

Última actualización: 2026-10-20.

## Catálogo ampliado (en curso)

- 17 categorías con sus parámetros de diseño en `backend/app/catalogo_esquema.json`: además de cámaras, switches,
  UPS, ONU, OLT y routers, ahora hay racks, gabinetes de intemperie, postes, radioenlaces PtP y PtMP, enlaces de
  internet, módulos SFP, splitters, cables de fibra, ODF, cajas de fibra y fuentes.
- 68 modelos base: reales de los datasheets y listados de obras, y genéricos de referencia marcados como tales.
- El formulario del catálogo se arma con el esquema; la tabla se puede filtrar por categoría.
- Los genéricos no cambian el cálculo automático (`seleccion_auto: false`). Detalle en [CATALOGO.md](CATALOGO.md).
- Falta: colocar antenas, cajas de fibra y acometidas de internet en el plano y calcular enlaces de radio y
  presupuesto óptico con estos parámetros (etapa 2).

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

## Etapa 1, parte 4: canalizaciones y cámaras de paso (2026-10-20)

- Herramienta **Canalización** (línea): enterrada (caño PEAD), aérea sobre cerco/postes o sobre pared/bandeja;
  diámetro (por defecto 40 mm) y marca de **cruce de calzada**.
- En las enterradas, las cámaras de paso se calculan solas: extremos, quiebres de más de 45° y cada 40 m
  (parámetros `dist_camaras_paso_m`, `giro_camara_paso`). Se ven como cuadraditos marrones. Las compartidas
  entre canalizaciones se cuentan una vez; una **Cámara de paso** puesta a mano (con su medida) reemplaza
  a la automática que esté a menos de 5 m.
- Listado, categoría "Obra civil": metros de canalización por tipo y diámetro (factor 1,03), zanjeo,
  cruces de calzada y cámaras de paso por medida.
- Pendiente: que fibra y energía se tiendan por las canalizaciones dibujadas (hoy van por el cerco).

## Etapa 1, parte 3: importar KML/KMZ y DXF (2026-10-20)

- "Importar KML, KMZ o DXF": el servidor agrupa la geometría por carpeta (KML) o capa (DXF) y en el
  diálogo se elige qué es cada grupo: perímetro, muro, obstáculo, cámara, gabinete, UPS, rack o solo
  dibujo de referencia (se ve en el mapa y no entra en el cálculo). Sugiere según el nombre de la capa.
- KML ya viene georreferenciado. El DXF se ubica con la calibración de 2 puntos (como los planos), con
  vista previa naranja y aviso si la escala no coincide con las unidades del dibujo ($INSUNITS).
- DXF: LINE, LWPOLYLINE, POLYLINE, CIRCLE, ARC, POINT e INSERT (bloque = punto con su nombre). Las
  líneas sueltas que se tocan se unen en una sola polilínea. DWG no: hay que guardarlo como DXF.
- Nueva dependencia: `ezdxf` (en requirements.txt; en el servidor correr `pip install -r requirements.txt`).
- Los tramos ciegos ahora siguen las esquinas del cerco.

## Etapa 1, parte 2: planos superpuestos (2026-10-20)

- Sección **Planos**: cargar PNG, JPG o PDF (se usa la primera página, renderizada en el navegador con
  pdf.js, incluido en `frontend/vendor/pdfjs`). Los archivos quedan en `datos/planos/<proyecto>/`.
- Se ubica con **calibración de 2 puntos**: un punto del plano y el mismo en el satélite, dos veces.
  Calcula escala y giro (similitud). Transparencia regulable, se puede ocultar o borrar.
- Cada plano pertenece a una planta (por ahora Exterior); sirve también para plantas interiores más adelante.

## Etapa 1, parte 1: óptica y obstáculos (2026-10-20)

- Cada cámara tiene altura (`altura_m`, por defecto 4 m) e inclinación (`inclinacion`, grados bajo la horizontal).
  Sin inclinación cargada se usa la automática: el borde superior del campo vertical toca el piso en el alcance.
- Con eso se calculan la zona ciega real bajo la cámara, el alcance efectivo sobre el piso y los PPM en el
  borde (por resolución si el modelo la tiene, o por el DORI del datasheet: identificación = 250 PPM).
  Avisos agrupados: PPM por debajo del mínimo (parámetro, 25 = detección) y cámaras que miran demasiado al piso.
- Herramientas Muro / pared (línea) y Obstáculo (polígono): cortan la línea de vista en planta. El cono
  se recorta en el mapa y la cobertura del perímetro los tiene en cuenta.
- Motor: `backend/app/engine/optica.py`, `geo.visible`; pruebas en `tests/test_optica.py`.

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
