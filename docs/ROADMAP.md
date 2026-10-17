# Plan por etapas

Basado en `Descripcion.docx` (especificación de Gastón). Las carpetas de obras (Barrios Privados,
Empresas, Parques Industriales) son referencia de criterios de diseño. Los presupuestos se hacen en
otro sistema y quedan fuera de esta aplicación.

1. **Diseño sobre mapa satelital** (en curso): perímetro, cámaras con cono de visión, cobertura y
   puntos ciegos, gabinetes, fibra, energía y listado de equipos.
2. **Catálogo completo**: Dahua, Hikvision, Cygnus y otras marcas; importar datos desde datasheet
   (PDF); reemplazar un equipo por otro y recalcular el diseño.
3. **Ingeniería de red y energía**: GPON (splitters, presupuesto óptico) o anillo; switches core;
   ancho de banda interno e internet, IP pública; caída de tensión por norma vigente (AEA 90364);
   gabinetes y tableros típicos con esquemas; centrales de monitoreo dimensionadas.
4. **Planos y fotos**: superponer PDF, imágenes y DWG/DXF calibrando escala; vectorizar; más
   adelante reconocimiento asistido de elementos; obra civil (columnas, brazos, canalizaciones,
   cámaras de paso dimensionadas).
5. **Usuarios, documentos e informes**: superadministrador fijo, roles, visor para clientes,
   almacenamiento de documentos por proyecto, informe técnico y planos exportables.
6. **Instalable y móvil**: instalador Windows/Linux; app Android de relevamiento con fotos,
   ubicación GPS y notas que se integran al proyecto; análisis de imágenes de cámaras existentes.
