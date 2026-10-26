# Prototipo v2 — ESP32-C3 Super Mini

Firmware para dos sensores Hall analogicos Allegro A1325, con el entorno
Arduino-ESP32. Se conserva el archivo `prototipo_v2.ino` y su formato de salida.

## Configuracion de placa

- Instalar el paquete de placas **esp32 by Espressif Systems** en Arduino IDE.
- Seleccionar **ESP32C3 Dev Module**, o la definicion especifica de la placa si esta disponible.
- Para el conector USB nativo, habilitar **USB CDC On Boot: Enabled**.
- Seleccionar el puerto USB correspondiente. El sketch comprueba que el destino sea ESP32-C3.
- La constante `SERIAL_BAUD` conserva el valor 460800. Si se usa un adaptador UART,
  el receptor debe usar esa velocidad; con USB CDC nativo, ese valor no determina
  el caudal fisico del enlace USB.

## Entradas analogicas

| Sensor | GPIO | Canal |
| --- | --- | --- |
| A1325 inferior | 0 | ADC1_CH0 |
| A1325 superior | 1 | ADC1_CH1 |

El programa configura lecturas de 12 bits (0 a 4095) y atenuacion `ADC_11db`
en ambos canales. En el ESP32-C3, el rango documentado con esa atenuacion es
aproximadamente 0 a 2,5 V. Las lecturas son cuentas crudas del ADC, no voltajes.
Los canales se leen consecutivamente, no en simultaneo.

Los A1325 requieren alimentacion de 4,5 a 5,5 V y su salida puede superar el
rango del ADC. **No conectar directamente su salida a los GPIO.** El equipo de
electronica debe definir el acondicionamiento, la masa comun y los niveles de
entrada admitidos antes de conectar los sensores. La atenuacion del ADC no es
una proteccion de entrada. No alimentar el A1325 a 3,3 V como sustituto de ese
acondicionamiento: queda fuera de su rango de alimentacion especificado.

La calibracion debe hacerse con el acondicionamiento definitivo instalado.
No hace falta conocer la relacion del divisor para normalizar las cuentas,
si la adaptacion conserva la forma de onda y no introduce saturacion ni
distorsiones relevantes. La configuracion del ADC debe revisarse si cambia
el rango de salida del circuito de acondicionamiento.

## Adquisicion y comandos

- Objetivo: 1000 pares de lecturas por segundo. Verificarlo con `intervalo_us`.
- `c`: calibra durante 10 segundos mientras se mueve la varilla.
- `z`: fija el origen en la siguiente muestra calibrada.
- No se descartan muestras por cambios de amplitud o vibraciones.
- La posicion transmitida es preliminar; el analisis posterior usa los datos crudos.

Abrir el receptor antes de calibrar para conservar los eventos. La cabecera de
mediciones se envia una vez en `setup()`; el receptor tambien debe conocerla
por si se conecta despues del arranque USB.

```text
tiempo_us,intervalo_us,raw1,raw2,calibrando,calibrado,posicion_mm
#CAL,tiempo_fin_us,tiempo_inicio_us,aceptada,min1,max1,min2,max2,periodo_mm
#ORIGEN,tiempo_us
```

La placa transmite estas lineas; no guarda archivos por si sola. El receptor
debe separar las mediciones y los eventos y contemplar reinicios y el desborde
del contador `micros()` de 32 bits.

## Fuentes

- [ADC de Arduino-ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/api/adc.html)
- [GPIO del ESP32-C3](https://docs.espressif.com/projects/esp-idf/en/latest/esp32c3/api-reference/peripherals/gpio.html)
- [USB CDC en Arduino-ESP32](https://docs.espressif.com/projects/arduino-esp32/en/latest/tutorials/cdc_dfu_flash.html)
- [Hoja de datos Allegro A1324/A1325/A1326](https://www.allegromicro.com/-/media/files/datasheets/a1324-5-6-datasheet.pdf)

La validacion de sintaxis en una computadora no sustituye compilar con
Arduino-ESP32 ni medir frecuencia, saturacion y recorrido con la placa real.
