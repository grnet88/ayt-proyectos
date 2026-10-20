# Catálogo de equipos

Las categorías y sus campos están en `backend/app/catalogo_esquema.json`. La pantalla Catálogo arma el formulario
con ese archivo, así que sumar un parámetro o una categoría no requiere tocar la interfaz.

Los modelos base están en `backend/app/catalogo_base.json`. Hay dos clases:

- **Reales:** tomados de datasheets y listados de materiales de obras de AyT (Cinco Lagos ABC, Cadaques, El Paso,
  Jockey). El campo `fuente` dice de dónde sale cada dato.
- **Genéricos de referencia** (`generico: true`, etiqueta "genérico" en la tabla): valores típicos de mercado para
  diseñar antes de elegir marca. Se duplican y se ajustan con el datasheet del modelo elegido.

Los switches y UPS nuevos tienen `seleccion_auto: false`: el cálculo no los elige solo, para no cambiar los diseños
existentes. Se habilitan desde el formulario ("Lo elige el cálculo automático").

## Categorías y para qué sirve cada parámetro

| Grupo | Categoría | Parámetros de diseño | Uso previsto en el cálculo |
| --- | --- | --- | --- |
| CCTV | Cámara | ángulos, DORI, IR, alcance de analítica, bitrate, PoE | Cobertura, PoE, ancho de banda y grabación (ya funciona) |
| Red | Switch | puertos PoE, presupuesto PoE, SFP, uso | Switch por gabinete (ya funciona) |
| Red | Router | puertos cobre y SFP, U de rack | Ocupación del rack central |
| Red | Módulo SFP | velocidad, alcance, potencia de emisión, sensibilidad | Presupuesto óptico de enlaces punto a punto por fibra |
| Enlaces | Radioenlace / antena | banda, ganancia, apertura, potencia, sensibilidad, capacidad real, alcance, clientes | Presupuesto de enlace y zona de Fresnel; capacidad contra el bitrate de las cámaras del otro extremo |
| Enlaces | Enlace de internet | tecnología, bajada, subida, IP fija, SLA | La subida limita las cámaras que se ven en remoto |
| Fibra | OLT | puertos PON, ONU por puerto, potencia, clase óptica | Presupuesto GPON (B+ 28 dB, C+ 32 dB) |
| Fibra | ONU | puertos LAN, sensibilidad | Margen óptico en cada gabinete |
| Fibra | Splitter | salidas, pérdida de inserción | Presupuesto GPON por rama |
| Fibra | Cable de fibra | tipo, pelos, atenuación por km, vano | Pérdida por distancia y tipo de tendido |
| Fibra | ODF, caja de fibra | puertos, fusiones | Cómputo de cajas, bandejas y fusiones |
| Racks y gabinetes | Rack, gabinete de intemperie, poste/soporte | U, medidas, carga, IP, altura | Ocupación de rack por U, láminas de gabinete y poste |
| Energía | UPS | VA, W, topología, autonomía, U | UPS por fuente (ya funciona) y autonomía |
| Energía | Fuente / inyector | tensión, corriente, montaje | Alimentación de radios y equipos no PoE |

## Valores de referencia usados en los genéricos

- Fibra monomodo: 0,35 dB/km a 1310 nm y 0,25 dB/km a 1550 nm.
- Splitters PLC, pérdida máxima: 1x2 3,8 dB, 1x4 7,4 dB, 1x8 10,7 dB, 1x16 13,9 dB, 1x32 17,2 dB.
- Radios de 5 GHz: para video se recomienda no pasar de 10 clientes por base y comparar la suma de bitrates con la
  capacidad real (no la nominal).
- 60 GHz: alcance de 2 km para mantener disponibilidad con lluvia; el respaldo de 5 GHz sostiene el enlace con menos
  capacidad.

## Orientación

Las categorías con `orientable: true` (cámara y radioenlace) se orientan en cada equipo colocado en el plano. La
orientación se guarda en el elemento, no en el modelo del catálogo.
