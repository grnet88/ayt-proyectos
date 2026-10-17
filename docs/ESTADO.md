# Estado del proyecto

Última actualización: 2026-10-17.

## Qué funciona (v0.1, etapa 1)

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
  eficiencia de fuentes 85 %, límite de caída 5 %.
- Reservas: 5 m de UTP por cámara, 20 m de fibra y 5 m de energía por gabinete, factor 1,05 de recorrido.
- Bitrate: 6 Mbps para 8 MP, 3 Mbps para 2 MP (H.265).

## Próximos pasos sugeridos

1. Gastón prueba el prototipo con un barrio real (por ejemplo Cinco Lagos ABC) y compara con su diseño.
2. Importar planos: imagen o PDF superpuesto al mapa, calibrando escala con una medida conocida.
3. Más tipos de dispositivos en el diseño: térmicas, radares, control de accesos (barreras, FaceID, molinetes).
4. Detalle de gabinetes y tableros (térmica, disyuntor, PAT) y esquemas típicos.
5. Usuarios y roles (superadministrador `aytroot`, visor para cliente).

## Pendientes de infraestructura

- Repositorio GitHub: falta que Gastón conecte su cuenta y cree el repositorio; mientras tanto el
  código está en la carpeta compartida del proyecto (`ayt-proyectos/`) con su historial git.
