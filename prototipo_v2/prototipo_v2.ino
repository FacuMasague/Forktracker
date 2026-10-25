#include <Arduino.h>
#include <math.h>

const uint8_t SENSOR1_PIN = A0; // Sensor inferior
const uint8_t SENSOR2_PIN = A1; // Sensor superior

const unsigned long SERIAL_BAUD = 460800UL; // Velocidad con la que los datos se envian
const unsigned long SAMPLE_INTERVAL_US = 1000UL; // Intervalo entre muestras, en microsegundos
const unsigned long CALIBRATION_DURATION_US = 10000000UL;

unsigned long ultimaMedUs = 0;
unsigned long intervaloRealUs = 0;
unsigned long inicioCalibracionUs = 0;

// Variables que controlan el proceso.
bool calibrando = false;
bool calibrado = false;
bool primeraMuestraCalibracion = false;
bool registroCalibracionPendiente = false;
bool registroOrigenPendiente = false;

int min1 = 0;
int max1 = 0;
int min2 = 0;
int max2 = 0;

float cero1 = 0.0f;
float cero2 = 0.0f;
float escala1 = 0.0f;
float escala2 = 0.0f;
float normalizada1 = 0.0f;
float normalizada2 = 0.0f;

const float PERIODO_MM = 12.0f;
const float PI_RAD = 3.1415927f;
const float DOS_PI_RAD = 2.0f * PI_RAD;
const float MM_POR_RADIAN = PERIODO_MM / DOS_PI_RAD;

bool seguimientoIniciado = false;
bool ceroPendiente = false;

float faseAnterior = 0.0f;
float posicionMM = 0.0f;

// Inicio del proceso de calibracion.
void inicioCalibracion() {
  calibrando = true;
  calibrado = false;
  primeraMuestraCalibracion = true;

  seguimientoIniciado = false;
  ceroPendiente = false;
  posicionMM = 0.0f;

  inicioCalibracionUs = micros();
}

// Actualiza la calibracion, registra maximos y minimos.
void actualizarCalibracion(int raw1, int raw2) {
  // La primera muestra inicializa los limites sin asumir el rango del ADC.
  if (primeraMuestraCalibracion) {
    min1 = max1 = raw1;
    min2 = max2 = raw2;
    primeraMuestraCalibracion = false;
  }

  if (raw1 < min1) min1 = raw1;
  if (raw1 > max1) max1 = raw1;

  if (raw2 < min2) min2 = raw2;
  if (raw2 > max2) max2 = raw2;
}

// Una vez terminada la calibracion, se calcula el centro y escala.
void terminarCalibracion() {
  calibrando = false;
  registroCalibracionPendiente = true;

  float amplitud1 = (max1 - min1) / 2.0f;
  float amplitud2 = (max2 - min2) / 2.0f;

  // Rechaza una calibracion sin muestras o sin variacion en algun canal.
  if (primeraMuestraCalibracion || amplitud1 <= 0.0f || amplitud2 <= 0.0f) {
    calibrado = false;
    return;
  }

  cero1 = (static_cast<float>(max1) + min1) / 2.0f;
  cero2 = (static_cast<float>(max2) + min2) / 2.0f;

  escala1 = 1.0f / amplitud1;
  escala2 = 1.0f / amplitud2;
  
  calibrado = true;
}

void adminComandos() {
  while (Serial.available() > 0) {
    char comando = Serial.read();

    if (comando == 'c' || comando == 'C') {
      inicioCalibracion();
    }
    else if ((comando == 'z' || comando == 'Z') && calibrado) {
      ceroPendiente = true;
    }
  }
}

void normalizarLecturas(int lectura1, int lectura2) {
  normalizada1 = (lectura1 - cero1) * escala1;
  normalizada2 = (lectura2 - cero2) * escala2;
}

// Convierte los cambios de fase en desplazamiento acumulado.
void actualizarPosicion() {
  float faseActual = atan2f(normalizada2, normalizada1);

  // La primera muestra calibrada establece el origen del seguimiento.
  if (!seguimientoIniciado || ceroPendiente) {
    faseAnterior = faseActual;
    posicionMM = 0.0f;
    seguimientoIniciado = true;
    ceroPendiente = false;
    registroOrigenPendiente = true;
    return;
  }

  float cambioFase = faseActual - faseAnterior;

  // Corrige el salto de representacion entre +PI y -PI.
  if (cambioFase > PI_RAD) {
    cambioFase -= DOS_PI_RAD;
  }
  else if (cambioFase < -PI_RAD) {
    cambioFase += DOS_PI_RAD;
  }

  posicionMM += cambioFase * MM_POR_RADIAN;
  faseAnterior = faseActual;
}

// Envia los eventos asociados a la muestra que acaba de procesarse.
void enviarEventos(unsigned long tiempoUs) {
  if (registroCalibracionPendiente) {
    Serial.print("#CAL,");
    Serial.print(tiempoUs);
    Serial.print(",");
    Serial.print(inicioCalibracionUs);
    Serial.print(",");
    Serial.print(calibrado ? 1 : 0);
    Serial.print(",");
    Serial.print(min1);
    Serial.print(",");
    Serial.print(max1);
    Serial.print(",");
    Serial.print(min2);
    Serial.print(",");
    Serial.print(max2);
    Serial.print(",");
    Serial.println(PERIODO_MM, 3);

    registroCalibracionPendiente = false;
  }

  if (registroOrigenPendiente) {
    Serial.print("#ORIGEN,");
    Serial.println(tiempoUs);

    registroOrigenPendiente = false;
  }
}

void setup() {
  Serial.begin(SERIAL_BAUD);
  Serial.println("tiempo_us,intervalo_us,raw1,raw2,calibrando,calibrado,posicion_mm");

  ultimaMedUs = micros();
}

void loop() {
  adminComandos();

  unsigned long nowUs = micros();

  // Se asegura de solo medir cuando paso 1ms (1000µs).
  unsigned long tiempoTranscurridoUs = nowUs - ultimaMedUs;
  if (tiempoTranscurridoUs < SAMPLE_INTERVAL_US) {
    return;
  }

  // Registra el intervalo observado antes de actualizar la referencia.
  intervaloRealUs = tiempoTranscurridoUs;
  ultimaMedUs = nowUs;

  int raw1 = analogRead(SENSOR1_PIN);
  int raw2 = analogRead(SENSOR2_PIN);

  if (calibrando) {
    actualizarCalibracion(raw1, raw2);

    if (nowUs - inicioCalibracionUs >= CALIBRATION_DURATION_US) {
      terminarCalibracion();
    }
  }

  if (calibrado) {
    normalizarLecturas(raw1, raw2);
    actualizarPosicion();
  }

  Serial.print(nowUs);
  Serial.print(",");
  Serial.print(intervaloRealUs);
  Serial.print(",");
  Serial.print(raw1);
  Serial.print(",");
  Serial.print(raw2);
  Serial.print(",");
  Serial.print(calibrando ? 1 : 0);
  Serial.print(",");
  Serial.print(calibrado ? 1 : 0);
  Serial.print(",");

  // Sin calibracion, la columna de posicion queda vacia.
  if (calibrado && seguimientoIniciado) {
    Serial.print(posicionMM, 3);
  }

  Serial.println();

  enviarEventos(nowUs);
}
