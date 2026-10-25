# VeriCall · detección visual de deepfakes

Aplicación local para analizar manipulación facial en videos y explicar una recomendación de tesorería. **Ahora ejecuta un modelo entrenado sobre los píxeles del video:** YuNet localiza los rostros y un Vision Transformer los clasifica. Incluye seis videos públicos con personas, reproductor, señal por instante, progreso, reglas de riesgo, historial SQLite e informes JSON.

## Abrir en este equipo

El entorno, los pesos y los seis videos ya están instalados en esta carpeta:

```bash
source .venv/bin/activate
python -m vericall.app
```

Abre **http://127.0.0.1:5000**. Selecciona una persona y su original o versión manipulada, declara autorización y pulsa **Analizar video**. También puedes subir MP4, MOV, AVI o WebM de hasta 100 MB y 2 minutos. El reproductor depende de los códecs del navegador; la decodificación para inferencia se hace con OpenCV.

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
5. Aplica reglas de monto, cuenta nueva, calidad y verificación alterna; guarda el resultado antes de mostrarlo.

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
  decision.py         Reglas de tesorería
  jobs.py             Cola acotada y progreso
  audit.py            SQLite transaccional
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
- La aplicación es local, sin autenticación multiusuario. La verificación alterna es una declaración del analista, no una comunicación comprobada. No hay integración bancaria ni videollamadas en vivo.

La base de datos está en `instance/vericall.sqlite3`. Las opciones de [.env.example](.env.example) se establecen con variables de entorno; el archivo no se carga automáticamente. Si el puerto 5000 está ocupado, ejecuta `VERICALL_PORT=5001 python -m vericall.app`. Si faltan o fallan hashes de archivos, repite `python scripts/download_assets.py`. Si una descarga falla, el script elimina el archivo parcial y reintenta; conserva las descargas correctas. La primera inferencia carga el modelo en memoria.

El JSONL de la versión anterior, si existe, permanece intacto; la interfaz nueva usa SQLite y no importa automáticamente ese historial.

## Relación con el proyecto final

La [revisión de fuentes y alcance](docs/proyecto_y_alcance.md) identifica lo ya definido en los dos entregables y los trabajos restantes. La [matriz de trazabilidad](docs/trazabilidad.md) vincula esta implementación con sesiones 3 y 4, escrito final y sustentación. El [diseño del detector](docs/modelo_y_validacion.md) distingue sus capacidades, supuestos y límites. Faltan validación independiente representativa, evaluación de sesgos, audio/identidad e integración y gobierno aprobados antes de un piloto organizacional.
