#include <Arduino.h>


const uint8_t SENSOR1_PIN = A0; // sensor inferior
const uint8_t SENSOR2_PIN = A1; // sensor superior


// Valores de calibración iniciales (ajusta según tu calibración)
// Las unidades de zero y scale hablan de tension electrica
float zero1  = 608.0; // 608 es el centro de lectura del sensor 1
float zero2  = 523.0; // 523 es el centro de lectura del sensor 2
// scale es la amplitud de la onda, convierte datos de la onda reales en distancias relativas proporcionales entre -1 y 1
float scale1 = 0.00241;
float scale2 = 0.00313;
// zero y scale normalizan las señales que devuelven los sensores


// Longitud de un ciclo completo en mm (dos imanes de 6 mm)
// (longitud de la onda)
const float PERIOD_MM = 12.0;


float prevAngle  = 0.0f; // el angulo indica en que parte del ciclo magnetico esta la varilla
long  cycleCount = 0;


// Variables de calibración automática
bool calibrated = false;
int  min1, max1, min2, max2;


// Variables para origen de posición
bool  originSet       = false;
long  originCycleCount = 0;
float originPosInCycle = 0.0f;


// Variable para medir tiempo relativo
unsigned long startMillis;


// Prepara el programa con el arduino se enciende o se reinicia
// setup es una funcion que Arduino ejecuta una sola vez al arrancar
void setup() { 
  Serial.begin(115200); // Inicia la comunicacion entre Arduino y la computadora. 115200 es la velocidad de comunicacion en baudios
  // Mensajes iniciales
  Serial.println("Escribe 'c' para calibrar sensores o 'z' para fijar el 0 mm.");
  // Cabecera para el fichero CSV
  Serial.println("tiempo_ms,posicion_mm"); // Prepara una salida con csv pero no guarda un archivo
  // Guarda el instante de inicio
  startMillis = millis(); // Devuelve cuantos milisegundos pasaron desde que arranco el programa. Guarda el valor en startMillis como referencia
}


void calibrateSensors(unsigned long duracion_ms) {
  // Reinicia máximos y mínimos
  // Arrancan al reves para que el minimo se reduzca y el maximo se aumente
  min1 = 1023; max1 = 0;
  min2 = 1023; max2 = 0;


  unsigned long start = millis(); // Guarda cuando empezo la calibracion
  // Bucle que actualiza el minimo y el maximo hasta que termine el tiempo especificado
  while (millis() - start < duracion_ms) {
    // Toma los valores crudos que deuvelve el programa
    int raw1 = analogRead(SENSOR1_PIN);
    int raw2 = analogRead(SENSOR2_PIN);


    if (raw1 < min1) min1 = raw1;
    if (raw1 > max1) max1 = raw1;
    if (raw2 < min2) min2 = raw2;
    if (raw2 > max2) max2 = raw2;


    delay(2);
  }


  // Calcula offsets y escalas
  // Calcula el zero de cada señal
  zero1 = (max1 + min1) / 2.0f;
  zero2 = (max2 + min2) / 2.0f;
  // Calcula la amplitud de la señal
  float amplitude1 = (max1 - min1) / 2.0f;
  float amplitude2 = (max2 - min2) / 2.0f;
  // Calcula los factores de escala
  scale1 = 1.0f / amplitude1;
  scale2 = 1.0f / amplitude2;


  // Devuelve los datos obtenidos al usuario
  Serial.println("Calibracion finalizada.");
  Serial.print("zero1 = "); Serial.println(zero1);
  Serial.print("zero2 = "); Serial.println(zero2);
  Serial.print("scale1 = "); Serial.println(scale1, 6);
  Serial.print("scale2 = "); Serial.println(scale2, 6);


  // Reinicia el tiempo de referencia tras calibrar
  startMillis = millis();
}


void setZeroReference(float angle) { // La funcion recibe el angulo calculado a partir de los dos sensores
  // Calcula la posición dentro del ciclo actual
  // angle + pi desplaza el interavlo de [-pi;pi] a [0;2*pi]
  // / 2*pi convierte el ciclo en un intervalo de [0;1]
  // * PERIOD_MM convierte la equivalencia del intervalo en distancias reales en 12mm
  originPosInCycle = (angle + M_PI) / (2.0f * M_PI) * PERIOD_MM;
  // Reinicia el contador de ciclos
  cycleCount = 0;
  // Guarda que se ha establecido el origen
  originSet = true;
  Serial.println("Origen establecido en la posicion actual.");
}

// funcion que ejecuta el programa entero de a bucle
void loop() {
  // Gestiona comandos de usuario
  if (Serial.available()) { // Serial.available() indica cuantos bytes recibidos estan pendientes en la lectura, si hay alguno entra en el bloque
    char cmd = Serial.read(); // Lee inputs del usuario
    if (cmd == 'c' || cmd == 'C') {
      Serial.println("Comenzando calibracion... mueve la varilla por todo su recorrido durante 10 segundos.");
      calibrateSensors(10000);
      calibrated = true;
      // Después de calibrar, borra el origen para obligar al usuario a fijar uno nuevo si quiere
      originSet = false;
      Serial.println("Calibracion lista. Si quieres fijar un punto de inicio, escribe 'z' y pulsa Enter.");
    }
    else if (cmd == 'z' || cmd == 'Z') {
      // Fijar origen al ángulo actual
      // Primero obtén una lectura para establecer el origen en el punto exacto en el que te encuentras
      int raw1 = analogRead(SENSOR1_PIN);
      int raw2 = analogRead(SENSOR2_PIN);
      float v1 = (raw1 - zero1) * scale1;
      float v2 = (raw2 - zero2) * scale2;
      float angle = atan2(v2, v1);
      setZeroReference(angle);
    }
  }


  // No hacemos nada más si no hay calibracion previa
  if (!calibrated) return;


  // Medición de la posición en mm usando los parámetros calibrados
  int raw1 = analogRead(SENSOR1_PIN);
  int raw2 = analogRead(SENSOR2_PIN);


  float v1 = (raw1 - zero1) * scale1;
  float v2 = (raw2 - zero2) * scale2;


  float angle = atan2(v2, v1);
  float delta = angle - prevAngle;


  // Gestionar saltos de ±PI (dirección del movimiento)
  if (delta >  M_PI) {
    delta -= 2.0f * M_PI;
    cycleCount--;
  }
  else if (delta < -M_PI) {
    delta += 2.0f * M_PI;
    cycleCount++;
  }


  prevAngle = angle;


  // Posición dentro del ciclo actual
  float posInCycle = (angle + M_PI) / (2.0f * M_PI) * PERIOD_MM;


  // Posición bruta sumando ciclos
  float positionMM = cycleCount * PERIOD_MM + posInCycle;


  // Si tenemos origen establecido, restamos la posición del origen
  if (originSet) {
    positionMM -= originPosInCycle;
    // Evitar valores negativos
    if (positionMM < 0) positionMM = 0.0f;
  }


  // Calcula el tiempo relativo desde la última calibración y envía ambos valores
  unsigned long tiempoRel = millis() - startMillis;
  Serial.print(tiempoRel);
  Serial.print(",");
  Serial.println(positionMM, 3); // imprime posición con 0.001 mm de resolución


  delay(5);
}
