# Receptor — computadora

Lee la transmision de `prototipo_v2.ino` por el puerto serie y guarda cada
sesion en una carpeta nueva. Probado con Python 3.13 en macOS.

## Instalacion

```bash
cd receptor
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
```

## Uso

```bash
python3 receptor.py --listar
python3 receptor.py --puerto /dev/cu.usbmodem1101
```

Con la placa conectada por USB, en macOS el puerto suele aparecer como
`/dev/cu.usbmodem…`. Durante el registro se escribe un comando y Enter:

| Comando | Accion |
| --- | --- |
| `c` | Envia `c` a la placa: calibracion de 10 s |
| `z` | Envia `z`: fija el origen (la placa lo ignora si no esta calibrada) |
| `q` | Termina y cierra los archivos (tambien Ctrl+C) |

Orden previsto: iniciar el receptor, `c` y mover la varilla, llevar el
mecanismo a la referencia, `z`, hacer la prueba, `q`.

En pantalla se muestra un resumen cada 2 s (cantidad, frecuencia recibida,
intervalo maximo, ultima lectura), no cada fila.

## Archivos de una sesion

Se crean en `sesiones/AAAA-MM-DD_HH-MM-SS/` en la raiz del proyecto
(se puede cambiar con `--carpeta`). Nunca se sobrescribe una sesion.

| Archivo | Contenido |
| --- | --- |
| `crudo.txt` | Copia exacta de los bytes recibidos, para diagnostico |
| `mediciones.csv` | Las 7 columnas de la placa, sin modificar, mas `segmento` y `tiempo_ext_us` |
| `eventos.csv` | `CAL`, `ORIGEN` y eventos del receptor (conexion, comando, desconexion, reinicio, fin) |
| `errores.csv` | Lineas invalidas con el motivo y su texto |

- **`segmento`**: aumenta en cada reconexion o reinicio detectado de la placa.
  Los tiempos solo son comparables dentro de un mismo segmento.
- **`tiempo_ext_us`**: `tiempo_us` corregido por el desborde de `micros()`
  (cada ~71,6 min). Un retroceso de `tiempo_us` menor a 2^31 us se interpreta
  como reinicio; uno mayor, como desborde.
- `eventos.csv` usa una sola tabla: en `ORIGEN` y en los eventos del receptor
  quedan vacias las columnas de calibracion. `hora_pc` es la hora de la computadora
  al procesar la linea, no el instante de la muestra.
- Las lineas vacias se ignoran; quedan igualmente en `crudo.txt`.

## Prueba sin placa

```bash
python3 prueba_receptor.py
```

Alimenta el receptor con una transmision simulada (filas cortadas y pegadas,
bytes corruptos, desborde, reinicios, eventos) y verifica los archivos.
No usa el puerto serie y no reemplaza la prueba con hardware.

## Pendiente de verificar con la placa

- Si abrir el puerto reinicia el ESP32-C3. El receptor deja DTR y RTS desactivadas;
  si igual se reinicia, la calibracion se pierde y hay que repetir `c`.
- Frecuencia real recibida y valores de `intervalo_us` con USB CDC.
- Si se conecta despues de calibrar, el receptor no tiene el `#CAL` de esa calibracion.
