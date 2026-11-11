"""Receptor de Forktracker: lee el puerto serie y guarda cada sesion en archivos.

Uso:
    python3 receptor.py --listar
    python3 receptor.py --puerto /dev/cu.usbmodem1101

Durante el registro, escribir un comando y Enter:
    c = calibrar, z = fijar cero, q = terminar (tambien Ctrl+C).
"""

import argparse
import csv
import queue
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

from protocolo import COLUMNAS_CAL, COLUMNAS_MEDICIONES, clasificar_linea

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    serial = None

BAUDIOS = 460800  # Debe coincidir con SERIAL_BAUD si se usa UART; con USB CDC no limita el caudal.
MODULO_MICROS = 2**32
MITAD_MODULO = 2**31
MAX_LINEA_BYTES = 4096
INTERVALO_ESTADO_S = 2.0
INTERVALO_FLUSH_S = 1.0
ESPERA_RECONEXION_S = 0.5
CARPETA_SESIONES = Path(__file__).resolve().parent.parent / "sesiones"

COLUMNAS_MEDICIONES_CSV = COLUMNAS_MEDICIONES + ["segmento", "tiempo_ext_us"]
# CAL y ORIGEN comparten archivo: las columnas que no aplican quedan vacias.
COLUMNAS_EVENTOS_CSV = (["hora_pc", "segmento", "tipo", "tiempo_ext_us", "tiempo_us"]
                        + COLUMNAS_CAL[1:] + ["detalle"])
COLUMNAS_ERRORES_CSV = ["hora_pc", "segmento", "n_linea", "motivo", "texto"]


def hora_pc():
    return datetime.now().isoformat(timespec="milliseconds")


class TiempoPlaca:
    """Extiende micros() de 32 bits y separa segmentos ante reinicios o reconexiones."""

    def __init__(self):
        self.segmento = 0
        self.ultimo_us = None
        self.ultimo_ext_us = None

    def nuevo_segmento(self):
        self.segmento += 1
        self.ultimo_us = None
        self.ultimo_ext_us = None

    def hay_mediciones(self):
        return self.ultimo_us is not None

    def medicion(self, t):
        """Devuelve (tiempo_ext_us, reinicio_detectado)."""
        reinicio = False
        if self.ultimo_us is None:
            ext = t
        elif t >= self.ultimo_us:
            ext = self.ultimo_ext_us + (t - self.ultimo_us)
        elif self.ultimo_us - t > MITAD_MODULO:
            # Desborde: el contador paso de cerca de 2^32 a cerca de cero.
            ext = self.ultimo_ext_us + (t - self.ultimo_us) % MODULO_MICROS
        else:
            # Retroceso que no puede ser un desborde: la placa arranco de nuevo.
            self.nuevo_segmento()
            ext = t
            reinicio = True
        self.ultimo_us, self.ultimo_ext_us = t, ext
        return ext, reinicio

    def evento(self, t):
        """Ubica un evento respecto de la ultima medicion, sin modificar el estado."""
        if self.ultimo_us is None:
            return t
        dif = (t - self.ultimo_us) % MODULO_MICROS
        if dif >= MITAD_MODULO:
            dif -= MODULO_MICROS
        return self.ultimo_ext_us + dif


class Sesion:
    """Separa la transmision en mediciones, eventos y errores, y la guarda en una carpeta."""

    def __init__(self, carpeta: Path, mostrar=print):
        carpeta.mkdir(parents=True, exist_ok=False)  # nunca sobrescribe una sesion
        self.carpeta = carpeta
        self.mostrar = mostrar

        self._archivos = []
        self._crudo = self._abrir("crudo.txt", binario=True)
        self._mediciones = csv.writer(self._abrir("mediciones.csv"))
        self._eventos = csv.writer(self._abrir("eventos.csv"))
        self._errores = csv.writer(self._abrir("errores.csv"))
        self._mediciones.writerow(COLUMNAS_MEDICIONES_CSV)
        self._eventos.writerow(COLUMNAS_EVENTOS_CSV)
        self._errores.writerow(COLUMNAS_ERRORES_CSV)

        self.tiempo = TiempoPlaca()
        self._pendiente = b""
        self.n_linea = 0
        self.total_mediciones = 0
        self.total_invalidas = 0
        self.ultima_medicion = None
        self._ventana_mediciones = 0
        self._ventana_intervalo_max = 0

    def _abrir(self, nombre, binario=False):
        if binario:
            f = open(self.carpeta / nombre, "wb")
        else:
            f = open(self.carpeta / nombre, "w", newline="", encoding="utf-8")
        self._archivos.append(f)
        return f

    # --- Segmentos y eventos propios del receptor ---

    def iniciar_segmento(self, tipo, detalle=""):
        self.tiempo.nuevo_segmento()
        self.evento_receptor(tipo, detalle)

    def terminar_segmento(self, tipo, detalle=""):
        # Una linea cortada por la desconexion se registra en vez de perderse.
        if self._pendiente:
            self._registrar_invalida(self._pendiente, "linea incompleta al terminar el segmento")
            self._pendiente = b""
        self.evento_receptor(tipo, detalle)

    def evento_receptor(self, tipo, detalle=""):
        self._eventos.writerow([hora_pc(), self.tiempo.segmento, tipo, "", ""]
                               + [""] * (len(COLUMNAS_CAL) - 1) + [detalle])

    # --- Procesamiento de la transmision ---

    def procesar_bytes(self, datos: bytes):
        self._crudo.write(datos)
        self._pendiente += datos
        *lineas, self._pendiente = self._pendiente.split(b"\n")
        for linea in lineas:
            self._procesar_linea(linea)
        if len(self._pendiente) > MAX_LINEA_BYTES:
            self._registrar_invalida(self._pendiente, "linea demasiado larga sin fin de linea")
            self._pendiente = b""

    def _procesar_linea(self, datos: bytes):
        self.n_linea += 1
        linea = clasificar_linea(datos)

        if linea.tipo == "medicion":
            ext, reinicio = self.tiempo.medicion(int(linea.campos[0]))
            if reinicio:
                self.evento_receptor("reinicio_detectado", "tiempo_us retrocedio")
                self.mostrar("Aviso: tiempo_us retrocedio, posible reinicio de la placa.")
            self._mediciones.writerow(linea.campos + [self.tiempo.segmento, ext])
            self.total_mediciones += 1
            self.ultima_medicion = linea.campos
            self._ventana_mediciones += 1
            self._ventana_intervalo_max = max(self._ventana_intervalo_max, int(linea.campos[1]))

        elif linea.tipo == "cal":
            ext = self.tiempo.evento(int(linea.campos[0]))
            self._eventos.writerow([hora_pc(), self.tiempo.segmento, "CAL", ext]
                                   + linea.campos + [""])
            aceptada = "aceptada" if linea.campos[2] == "1" else "RECHAZADA"
            self.mostrar(f"Calibracion {aceptada}: canal 1 [{linea.campos[3]}, {linea.campos[4]}], "
                         f"canal 2 [{linea.campos[5]}, {linea.campos[6]}]")

        elif linea.tipo == "origen":
            ext = self.tiempo.evento(int(linea.campos[0]))
            self._eventos.writerow([hora_pc(), self.tiempo.segmento, "ORIGEN", ext, linea.campos[0]]
                                   + [""] * (len(COLUMNAS_CAL) - 1) + [""])
            self.mostrar("Origen fijado.")

        elif linea.tipo == "cabecera":
            # Si ya habia mediciones, la cabecera indica que la placa arranco de nuevo.
            if self.tiempo.hay_mediciones():
                self.iniciar_segmento("cabecera", "nuevo segmento: la placa reinicio")
                self.mostrar("Aviso: se recibio la cabecera de nuevo, posible reinicio de la placa.")
            else:
                self.evento_receptor("cabecera")

        elif linea.tipo == "invalida":
            self._registrar_invalida(datos, linea.error)

    def _registrar_invalida(self, datos: bytes, motivo):
        texto = datos.rstrip(b"\r\n").decode("ascii", errors="backslashreplace")
        self._errores.writerow([hora_pc(), self.tiempo.segmento, self.n_linea, motivo, texto])
        self.total_invalidas += 1

    # --- Estado y cierre ---

    def estado(self, segundos):
        """Resumen de una linea; reinicia la ventana de conteo."""
        frecuencia = self._ventana_mediciones / segundos if segundos > 0 else 0.0
        texto = (f"{self.total_mediciones} mediciones ({frecuencia:.0f}/s, "
                 f"intervalo max {self._ventana_intervalo_max} us) | invalidas {self.total_invalidas}")
        if self.ultima_medicion:
            _, _, raw1, raw2, calibrando, calibrado, posicion = self.ultima_medicion
            texto += f" | raw {raw1},{raw2}"
            if calibrando == "1":
                texto += " | calibrando"
            elif calibrado == "1":
                texto += f" | posicion {posicion} mm"
            else:
                texto += " | sin calibrar"
        self._ventana_mediciones = 0
        self._ventana_intervalo_max = 0
        return texto

    def flush(self):
        for f in self._archivos:
            f.flush()

    def cerrar(self):
        if self._pendiente:
            self._registrar_invalida(self._pendiente, "linea incompleta al cerrar")
            self._pendiente = b""
        for f in self._archivos:
            f.close()


# --- Puerto serie y teclado ---

def listar_puertos():
    puertos = list(list_ports.comports())
    if not puertos:
        print("No se encontraron puertos serie.")
    for p in puertos:
        print(f"  {p.device}  ({p.description})")


def abrir_puerto(nombre):
    ser = serial.Serial()
    ser.port = nombre
    ser.baudrate = BAUDIOS
    ser.timeout = 0.05
    # En el USB Serial/JTAG del C3, DTR/RTS pueden reiniciar la placa al abrir el puerto.
    # Se dejan desactivadas; el efecto real queda pendiente de verificar con la placa.
    ser.dtr = False
    ser.rts = False
    ser.open()
    return ser


def leer_teclado(cola):
    for linea in sys.stdin:
        cola.put(linea.strip().lower())
    cola.put("q")


def atender_comando(comando, ser, sesion):
    """Devuelve False si hay que terminar."""
    if comando == "q":
        return False
    if comando not in ("c", "z"):
        if comando:
            print("Comandos: c = calibrar, z = fijar cero, q = terminar")
        return True
    if ser is None:
        print(f"Sin conexion: el comando '{comando}' no se envio.")
        return True
    ser.write(comando.encode("ascii"))
    sesion.evento_receptor("comando", comando)
    print(f"Comando '{comando}' enviado.")
    return True


def main():
    parser = argparse.ArgumentParser(description="Receptor de datos de Forktracker")
    parser.add_argument("--puerto", help="por ejemplo /dev/cu.usbmodem1101")
    parser.add_argument("--listar", action="store_true", help="lista los puertos y termina")
    parser.add_argument("--carpeta", type=Path, default=CARPETA_SESIONES,
                        help="carpeta donde se crean las sesiones")
    args = parser.parse_args()

    if serial is None:
        print("Falta pyserial. Instalar con: python3 -m pip install -r requirements.txt")
        return 1

    if args.listar or not args.puerto:
        listar_puertos()
        return 0

    try:
        ser = abrir_puerto(args.puerto)
    except (serial.SerialException, OSError) as e:
        print(f"No se pudo abrir {args.puerto}: {e}")
        print("Puertos disponibles:")
        listar_puertos()
        return 1

    carpeta = args.carpeta / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    sesion = Sesion(carpeta)
    sesion.iniciar_segmento("conexion", args.puerto)
    print(f"Guardando en {carpeta}")
    print("Comandos: c = calibrar, z = fijar cero, q = terminar (y Enter)")

    cola = queue.Queue()
    threading.Thread(target=leer_teclado, args=(cola,), daemon=True).start()

    ultimo_estado = ultimo_flush = time.monotonic()
    seguir = True
    try:
        while seguir:
            while not cola.empty():
                seguir = atender_comando(cola.get(), ser, sesion) and seguir

            if ser is None:
                try:
                    ser = abrir_puerto(args.puerto)
                    sesion.iniciar_segmento("reconexion", args.puerto)
                    print("Conexion recuperada.")
                except (serial.SerialException, OSError):
                    time.sleep(ESPERA_RECONEXION_S)
                    continue

            try:
                datos = ser.read(ser.in_waiting or 1)
            except (serial.SerialException, OSError) as e:
                sesion.terminar_segmento("desconexion", str(e))
                ser.close()
                ser = None
                print("Se perdio la conexion. Reintentando...")
                continue

            if datos:
                sesion.procesar_bytes(datos)

            ahora = time.monotonic()
            if ahora - ultimo_flush >= INTERVALO_FLUSH_S:
                sesion.flush()
                ultimo_flush = ahora
            if ahora - ultimo_estado >= INTERVALO_ESTADO_S:
                print(sesion.estado(ahora - ultimo_estado))
                ultimo_estado = ahora
    except KeyboardInterrupt:
        pass
    finally:
        if ser is not None:
            ser.close()
        sesion.terminar_segmento("fin")
        sesion.cerrar()

    print(f"Sesion cerrada: {sesion.total_mediciones} mediciones, "
          f"{sesion.total_invalidas} lineas invalidas. Archivos en {carpeta}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
