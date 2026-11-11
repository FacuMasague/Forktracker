"""Clasificacion y validacion de las lineas que transmite prototipo_v2.ino."""

import re
from dataclasses import dataclass, field

CABECERA_MEDICIONES = "tiempo_us,intervalo_us,raw1,raw2,calibrando,calibrado,posicion_mm"
COLUMNAS_MEDICIONES = CABECERA_MEDICIONES.split(",")
COLUMNAS_CAL = ["tiempo_fin_us", "tiempo_inicio_us", "aceptada",
                "min1", "max1", "min2", "max2", "periodo_mm"]
COLUMNAS_ORIGEN = ["tiempo_us"]

_ENTERO = re.compile(r"\d+")
_DECIMAL = re.compile(r"\d+\.\d+")
_BANDERA = re.compile(r"[01]")

# posicion_mm no se valida (None): es preliminar y no debe invalidar las lecturas crudas.
_PATRONES_MEDICION = [_ENTERO, _ENTERO, _ENTERO, _ENTERO, _BANDERA, _BANDERA, None]
_PATRONES_CAL = [_ENTERO, _ENTERO, _BANDERA, _ENTERO, _ENTERO, _ENTERO, _ENTERO, _DECIMAL]
_PATRONES_ORIGEN = [_ENTERO]


@dataclass
class Linea:
    tipo: str     # "medicion", "cal", "origen", "cabecera", "vacia" o "invalida"
    texto: str    # linea decodificada, sin fin de linea
    campos: list[str] = field(default_factory=list)  # valores tal como llegaron
    error: str = ""


def _primer_campo_invalido(valores, patrones):
    for i, (valor, patron) in enumerate(zip(valores, patrones)):
        if patron is not None and not patron.fullmatch(valor):
            return i
    return None


def clasificar_linea(datos: bytes) -> Linea:
    datos = datos.rstrip(b"\r\n")
    try:
        texto = datos.decode("ascii")
    except UnicodeDecodeError:
        texto = datos.decode("ascii", errors="backslashreplace")
        return Linea("invalida", texto, error="caracteres no ASCII")

    if texto == "":
        return Linea("vacia", texto)
    if texto == CABECERA_MEDICIONES:
        return Linea("cabecera", texto)

    partes = texto.split(",")

    if texto.startswith("#"):
        nombre, valores = partes[0], partes[1:]
        if nombre == "#CAL":
            tipo, columnas, patrones = "cal", COLUMNAS_CAL, _PATRONES_CAL
        elif nombre == "#ORIGEN":
            tipo, columnas, patrones = "origen", COLUMNAS_ORIGEN, _PATRONES_ORIGEN
        else:
            return Linea("invalida", texto, error=f"evento desconocido {nombre}")
    else:
        tipo, columnas, patrones, valores = "medicion", COLUMNAS_MEDICIONES, _PATRONES_MEDICION, partes

    if len(valores) != len(columnas):
        return Linea("invalida", texto,
                     error=f"{tipo}: {len(valores)} campos, se esperaban {len(columnas)}")

    i = _primer_campo_invalido(valores, patrones)
    if i is not None:
        return Linea("invalida", texto, error=f"{tipo}: {columnas[i]} = {valores[i]!r}")

    return Linea(tipo, texto, valores)
