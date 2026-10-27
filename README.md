# VeriCall · verificación de deepfakes durante la videollamada

Prueba de concepto local: VeriCall **monitorea en vivo** el rostro de quien llama y, cuando pide una transferencia, recomienda autorizarla, verificarla por canal alterno o bloquearla (entregable 2). Después, una persona toma la decisión final con reglas de autoridad, y todo queda en una bitácora encadenada por hashes. YuNet localiza los rostros y un Vision Transformer entrenado los clasifica, en CPU (~40–60 ms por cuadro).

Hay dos modos:

- **Llamada en vivo** (pantalla inicial): tres fuentes posibles. **Simulación**: llamada entrante que reproduce un video público, original o deepfake, o **un video propio**. Este se reproduce solo en el navegador y no se sube; la bitácora guarda su SHA-256. **Cámara**: tu webcam como interlocutor real. **Zoom / Meet**: compartes la ventana de la videollamada real y VeriCall analiza a quien aparece en ella. El navegador envía ~2 cuadros por segundo; el servidor los analiza y los descarta, y solo conserva puntajes y posiciones de los rostros.
- **Analizar grabación**: el flujo anterior sobre un video completo (24 instantes).

## Abrir en este equipo

El entorno, los pesos y los seis videos ya están instalados en esta carpeta:

```bash
source .venv/bin/activate
python -m vericall.app
```

Abre **http://127.0.0.1:5000** (en Chrome; la cámara y la pantalla compartida exigen `127.0.0.1` o `localhost`).

### Guion sugerido para la sustentación (≈ 4 min)

1. **Ataque.** En *Simulación* elige *Persona 01 · Versión manipulada*, marca la autorización y pulsa **Iniciar monitoreo** → **Contestar**. En ~10 s aparece el recuadro sobre el rostro y luego la alerta «Posible deepfake».
2. **Solicitud de pago.** **Mientras se ve la alerta**, pulsa **Evaluar transferencia**: la ventana reciente está en ≥ 75, así que el sistema recomienda *Bloquear y escalar* y explica sus razones. Si evalúas en un tramo con señal más baja, este clip suele quedar en 60–70: *Verificar por otro canal*. El resultado depende del momento, y eso también se puede explicar.
3. **Control humano.** Intenta liberar el pago como *Analista*: el sistema lo impide, porque solo Seguridad puede liberar un bloqueo crítico, con verificación alterna y sin ser quien lo solicitó. Registra el rechazo como *Área de seguridad*. Se muestra el tiempo contra el objetivo de ≤ 15 min.
4. **Interlocutor real.** Finaliza la llamada y repite con *Persona 04 · Original* o con **Cámara**: con un rostro auténtico la recomendación suele ser *Autorizar: el analista confirma*. No está garantizado: la webcam está fuera del dominio de entrenamiento y puede quedar en zona incierta, lo que también sirve para explicar los límites del modelo.
5. **Auditoría.** En la bitácora, el indicador «Bitácora íntegra» recalcula la cadena de hashes. Exporta el JSON de la decisión para mostrar qué se puede reconstruir.

Resultados medidos en vivo, con 2 cuadros por segundo sobre cada clip completo:

| Llamada simulada | Señal usada | Recomendación |
|---|---:|---|
| Persona 04 / 05 · Original | 19 | Autorizar: el analista confirma |
| Persona 01 · Original | 35 | Verificar por otro canal |
| Persona 01 · Manipulada | 70 (≥ 75 durante la alerta) | Verificar / Bloquear |
| Persona 05 · Manipulada | 60 | Verificar por otro canal |
| Persona 04 · Manipulada | 22 | **Autorizar: falso negativo** |

**Videos propios del grupo (recomendado).** Graben a un compañero hablando a cámara, como si pidiera la transferencia (video real), y hagan un cambio de rostro consentido con otro compañero (deepfake). En *Simulación → O usa un video propio* se cargan como llamada entrante. Para deepfakes famosos públicos, ábrelos en otra pestaña y usa *Zoom / Meet* para compartirla. Pruébalos antes de clase: el modelo puede no detectarlos.

Caso honesto para las preguntas: *Persona 04 · Versión manipulada* es el falso negativo conocido del modelo y en vivo **recibe recomendación de autorizar**. Muestra por qué la confirmación humana y el canal alterno son controles necesarios, no opcionales, y por qué el entregable 2 incluye la regla de montos y cuentas nuevas, que fuerza revisión sin importar el puntaje.

En **Analizar grabación**, selecciona una persona y su original o versión manipulada, declara autorización y pulsa **Analizar video**. También puedes subir MP4, MOV, AVI o WebM de hasta 100 MB y 2 minutos. El reproductor depende de los códecs del navegador; la decodificación para inferencia se hace con OpenCV.

## Instalar en otro equipo

Python 3.11 o posterior, con ruedas de PyTorch/OpenCV disponibles para el sistema. Verificado en macOS Apple Silicon con Python 3.13.9 y CPU. No se requieren cuentas, claves ni APIs de pago.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/download_assets.py
python -m vericall.app
```

En Windows activa con `.venv\Scripts\activate`. La descarga inicial contiene unos 343 MB de pesos, 0,23 MB del localizador de rostros y 20 MB de videos. El script reutiliza archivos íntegros y verifica SHA-256. El análisis posterior funciona sin Internet. Los binarios descargados están excluidos de Git; el manifiesto permite reconstruirlos.

## Qué hace el detector

1. Valida el video y decodifica 24 instantes distribuidos uniformemente.
2. Localiza hasta cuatro rostros por instante y clasifica sus recortes con pesos Safetensors locales.
3. Toma el máximo por rostro en cada instante y calcula la media temporal. Conserva los resultados individuales para inspección.
4. La clasificación binaria usa 0,5. Además, la zona 0,25–0,75 se trata como incierta para la decisión. Menos de cuatro instantes con rostros o cobertura inferior al 50 % produce evidencia insuficiente.
5. Aplica reglas de monto, cuenta nueva y calidad; guarda el resultado antes de mostrarlo. Rangos del entregable 2: 0–30 autorizar con confirmación del analista; 31–70 verificar por canal alterno; 71–100 bloquear y escalar.

En vivo, la señal se recalcula con cada cuadro sobre una ventana de los últimos 16 cuadros (~8 s). Al evaluar una transferencia se usa **la evidencia más desfavorable** entre toda la llamada y esa ventana. Así, un ataque que empieza a mitad de la llamada no queda diluido por los minutos anteriores.

### Decisión humana final y bitácora

| Recomendación | Quién puede liberar el pago | Requisito |
|---|---|---|
| Autorizar (0–30) | Analista o Seguridad | Confirmación del analista |
| Verificar por otro canal (31–70 o regla obligatoria) | Analista o Seguridad | Verificación alterna descrita |
| Bloquear y escalar (71–100) | Solo Seguridad | Verificación alterna, y una persona distinta del analista que solicitó la evaluación |

Cualquier rol puede rechazar. Cada decisión admite una sola resolución inmutable, que registra el tiempo transcurrido frente al objetivo de 15 minutos. Cada registro guarda el hash del anterior: `GET /api/audit/verify` recalcula la cadena y señala el primer registro alterado. Los roles se declaran sin autenticación; es una limitación del prototipo.

El puntaje visual **no es una probabilidad calibrada de fraude**. La clasificación «original» no verifica identidad. Un video sin rostros tampoco se considera auténtico. El modelo trabaja sobre imágenes: no analiza audio, voz ni sincronía labial y puede omitir deepfakes nuevos o bien elaborados.

## Resultados reales de la demostración

Se eligieron los IDs 1, 4 y 5 del dataset por tamaño de descarga antes de observar las predicciones. Se evaluaron los seis archivos, sin ocultar el caso fallado:

| Muestra | Referencia del editor | Señal de manipulación | Clasificación del modelo |
|---|---|---:|---|
| `real_01` | Original | 33,6/100 | Original, zona incierta |
| `fake_01` | Deepfake | 70,4/100 | Deepfake, zona incierta |
| `real_04` | Original | 19,4/100 | Original |
| `fake_04` | Deepfake | 21,7/100 | **Original: falso negativo** |
| `real_05` | Original | 20,9/100 | Original |
| `fake_05` | Deepfake | 57,4/100 | Deepfake, zona incierta |

Coinciden cinco clasificaciones de seis; detecta dos de tres deepfakes. Este resultado es una demostración pequeña de desarrollo, **no una estimación válida del desempeño real**. La interfaz muestra la discrepancia en `fake_04`. El [informe completo](reports/sample_evaluation.json) conserva las salidas por instante, hashes, modelo y revisión.

## Pruebas y reevaluación

```bash
python -m pytest -q                 # Controles, errores, cola y bitácora
python -m pytest -q --run-model     # También inferencia real, sin red
python scripts/evaluate_samples.py # Reevalúa los seis videos e incluye todos los errores
```

Prueba opcional de navegador:

```bash
python -m pip install -r requirements-dev.txt
python -m playwright install chromium
python scripts/browser_smoke.py
```

Si ya tienes Chrome en macOS, puedes evitar descargar Chromium:

```bash
python scripts/browser_smoke.py --chrome '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome'
```

## Estructura

```text
vericall/
  app.py              API y servidor local
  detector.py         YuNet y ViT; verificación y carga local de pesos
  pipeline.py         Muestreo, rostros, inferencia y agregación
  live.py             Sesiones de llamada en vivo, ventana reciente y evidencia
  decision.py         Reglas de tesorería y resolución humana (roles, canal alterno, SLA)
  jobs.py             Cola acotada y progreso
  audit.py            SQLite de solo inserción encadenado por hashes
  static/             Interfaz, reproductor y gráfico de resultados
config/assets.json    URLs exactas, revisiones, hashes y etiquetas de referencia
sample_data/public/   Seis videos descargados, sin modificar (fuera de Git)
sample_data/videos/   Figuras sintéticas para pruebas de ausencia de rostros
models/               Pesos locales descargados (fuera de Git)
scripts/              Descarga, evaluación y prueba de navegador
tests/                Pruebas automáticas
reports/              Evaluación reproducible de las seis muestras
docs/                 Fuentes académicas, alcance y matriz de trazabilidad
instance/             Bitácora local, fuera de Git
```

## Fuentes, privacidad y operación

- Videos: [Unidata / ud-biometrics](https://huggingface.co/datasets/ud-biometrics/deepfake-dataset), licencia publicada CC BY-NC-ND 4.0. Se conservan bytes originales para esta demostración académica. Detalles en [sample_data/README.md](sample_data/README.md).
- Clasificador: [prithivMLmods/Deep-Fake-Detector-v2-Model](https://huggingface.co/prithivMLmods/Deep-Fake-Detector-v2-Model), Apache-2.0.
- Localizador: [OpenCV YuNet](https://github.com/opencv/opencv_zoo/tree/main/models/face_detection_yunet), licencia MIT del directorio del modelo.
- Los videos subidos se eliminan al terminar el trabajo, incluso al fallar. No se guardan recortes, miniaturas ni video en SQLite. Los seis ejemplos públicos permanecen como archivos de prueba. La bitácora sí conserva monto, declaraciones, métricas, hashes y resultados.
- La cola permite tres trabajos pendientes y una inferencia simultánea. Los estados temporales expiran a los 30 minutos; los informes permanecen en la bitácora.
- En vivo, los cuadros se procesan en memoria y se descartan. Las sesiones expiran tras 10 minutos sin actividad; hay como máximo tres llamadas simultáneas.
- La aplicación es local, sin autenticación multiusuario. La verificación alterna es una declaración de quien resuelve, no una comunicación comprobada. La integración con Zoom/Meet es por pantalla compartida, no por la API de la plataforma. No hay integración bancaria ni análisis de audio.
- La cadena de hashes detecta ediciones o borrados intermedios, pero no el borrado de los últimos registros ni la reescritura completa de la base. Para eso haría falta anclar el último hash fuera del equipo.

La base de datos está en `instance/vericall.sqlite3`. Las opciones de [.env.example](.env.example) se establecen con variables de entorno; el archivo no se carga automáticamente. Si el puerto 5000 está ocupado, ejecuta `VERICALL_PORT=5001 python -m vericall.app`. Si faltan o fallan hashes de archivos, repite `python scripts/download_assets.py`. Si una descarga falla, el script elimina el archivo parcial y reintenta; conserva las descargas correctas. La primera inferencia carga el modelo en memoria.

El JSONL de la versión anterior, si existe, permanece intacto; la interfaz nueva usa SQLite y no importa automáticamente ese historial.

## Relación con el proyecto final

La [revisión de fuentes y alcance](docs/proyecto_y_alcance.md) identifica lo ya definido en los dos entregables y los trabajos restantes. La [matriz de trazabilidad](docs/trazabilidad.md) vincula esta implementación con sesiones 3 y 4, escrito final y sustentación. El [diseño del detector](docs/modelo_y_validacion.md) distingue sus capacidades, supuestos y límites. Faltan validación independiente representativa, evaluación de sesgos, audio/identidad e integración y gobierno aprobados antes de un piloto organizacional.
