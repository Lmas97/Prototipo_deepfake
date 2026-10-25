# VeriCall · prototipo local

Demostración académica de una **recomendación para una transferencia solicitada por videollamada**. Procesa videos AVI sintéticos reales, extrae señales técnicas, combina reglas de transacción y muestra puntaje, motivos, acción y registro de auditoría. **No detecta deepfakes, no autentica a una persona y no mueve dinero.**

El alcance y los criterios están en [docs/proyecto_y_alcance.md](docs/proyecto_y_alcance.md); la relación con los avances académicos está en [docs/trazabilidad.md](docs/trazabilidad.md). Los PDF y Word originales permanecen en la carpeta de trabajo, pero `.gitignore` evita redistribuirlos al publicar el repositorio.

## Requisitos e instalación

- Python 3.11 o posterior y `pip`.
- macOS, Windows o Linux con una instalación de OpenCV capaz de leer AVI MJPEG; se probó en macOS con Python 3.13.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

En Windows, sustituye la activación por `.venv\Scripts\activate`.

## Ejecutar y probar

```bash
python -m vericall.app
```

Abre <http://127.0.0.1:5000>. Marca la declaración de consentimiento, elige `Normal`, `Alerta` o `Inválido` y pulsa **Analizar video y evaluar**. `Normal` debe mostrar 0/100 y recomendación pendiente de confirmación del analista. `Alerta` debe mostrar 80/100 y bloqueo con escalamiento. `Inválido` debe mostrar un error legible. Puedes descargar los AVI desde la interfaz y volver a subirlos con **Cargar mi propio video y datos**. El archivo subido se borra después del análisis.

```bash
python -m pytest -q
```

Para regenerar los videos incluidos:

```bash
python sample_data/generate_videos.py
```

## Archivos de prueba

| Archivo | Tipo | Uso / salida esperada |
|---|---|---|
| `sample_data/videos/moving_shapes.avi` | Sintético, figuras en movimiento, sin personas ni audio | Caso normal: 36 cuadros, sin congelamiento, puntaje 0 con los datos predefinidos. |
| `sample_data/videos/frozen_shapes.avi` | Sintético, figuras fijas | Caso de alerta: 36 cuadros, transición congelada, puntaje 80 junto con cuenta nueva y monto alto. |
| `sample_data/invalid/not_a_video.txt` | Texto sintético | Caso inválido: formato rechazado. |
| `sample_data/cases.json` | Datos ficticios | Entradas y acciones esperadas de los tres casos. |

Todo el material de prueba fue generado para este repositorio; no usa videos de terceros ni requiere descarga adicional. El equipo debe decidir la licencia antes de publicar el repositorio. Estos videos prueban el flujo de decodificación y reglas, **no** la exactitud frente a fraudes reales.

## Estructura

```text
vericall/                 Interfaz Flask, procesamiento de video, reglas y auditoría
sample_data/              Tres casos, dos videos sintéticos y generador reproducible
tests/                    Pruebas del video y del recorrido web
docs/                     Alcance, criterios y trazabilidad académica
instance/                 Bitácora local JSONL (ignorada por Git)
requirements.txt          Dependencias
.env.example              Opciones de entorno
```

## Datos y límites

La bitácora `instance/decisions.jsonl` guarda ID, fecha UTC, SHA-256 del video, entradas, métricas, motivos, versión de reglas y acción. No conserva cuadros ni el archivo subido. Se puede cambiar la ruta con `VERICALL_AUDIT_PATH` y el límite de carga con `VERICALL_MAX_UPLOAD_MB`. La declaración de verificación alterna es manual y **no comprobada**. Los pesos del puntaje son una propuesta técnica, no un modelo validado. Se requieren datos etiquetados, consentimiento verificable, evaluación de sesgos, controles de acceso e integración con los sistemas corporativos antes de considerar un piloto real.

Si OpenCV no abre un video externo, convierte el archivo a AVI MJPEG o MP4 compatible; la aplicación rechaza videos sin cuadros decodificables, de más de 900 cuadros, o resolución superior a 1920×1080. Para problemas de instalación, crea de nuevo el entorno con una versión de Python compatible y repite `pip install -r requirements.txt`.
