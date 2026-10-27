# Verificación de VeriCall v2

Fecha local: 25 de octubre de 2026. Entorno comprobado: macOS Apple Silicon, Python 3.13.9, ejecución CPU. Las dependencias se instalaron en `.venv`; `pip check` no encontró incompatibilidades.

Resultado ejecutado: `python -m pytest -q --run-model` terminó con **21 pruebas aprobadas**. La prueba de Chrome también terminó correctamente. PyTorch 2.14.1 y Transformers 4.57.6 fueron las versiones utilizadas en este equipo.

## Detección real ejecutada

`python scripts/evaluate_samples.py` ejecutó el modelo sobre los seis videos descargados. El [informe JSON](../reports/sample_evaluation.json) conserva salidas por instante, tiempos observados, hashes, etiquetas de referencia, revisión del modelo y todos los errores. La clase binaria coincide en cinco casos; hay dos deepfakes detectados de tres y un falso negativo (`fake_04`). Tres casos quedan en zona incierta para una decisión de autenticidad.

El clasificador no recibió etiquetas, nombres de personas ni la etiqueta del dataset. La prueba de inferencia también ejecutó un video manipulado renombrado como `video_completamente_real.mp4` y conservó la clasificación de deepfake. Esto verifica independencia del nombre, no robustez ante cambios de distribución.

## Pruebas del software

- Validación de montos, consentimiento, formato y límites de carga.
- Video de texto disfrazado como MP4 rechazado por el decodificador.
- Videos de figuras sin rostros devuelven evidencia insuficiente y no ejecutan el clasificador facial.
- Cuenta nueva, monto alto, calidad insuficiente y ausencia de verificación alterna fuerzan revisión.
- Incertidumbre y cobertura facial insuficiente impiden recomendar autorización.
- Un puntaje alto bloquea; el resultado visual no se altera por el contexto de la transacción.
- Cola limitada, errores controlados y eliminación del archivo temporal.
- Fallo de bitácora impide publicar una decisión; exportación e historial recuperan el registro guardado.
- Ausencia de pesos o configuración dañada produce error, sin puntuación inventada.

Las pruebas rápidas inyectan un analizador controlado cuando verifican API, cola y almacenamiento. Esas pruebas no miden exactitud del modelo. La opción `--run-model` ejecuta adicionalmente el detector real con archivos públicos y modo offline de Hugging Face.

## Prueba real de navegador

`scripts/browser_smoke.py`, ejecutado con Chrome, comprobó: carga de los seis ejemplos; reproducción MP4 y MOV; detección real del ejemplo `fake_01`; exportación JSON; discrepancia visible de `fake_04`; carga del mismo deepfake con otro nombre; error legible ante MP4 inválido; historial; ausencia de errores JavaScript y ausencia de desbordamiento horizontal a 390 px de ancho. Usa una base SQLite temporal, separada de la bitácora del usuario.

## Lo que no se ha validado

No se ha medido desempeño con una muestra independiente grande, nuevos generadores, ataques en llamadas en vivo, audio, grupos demográficos ni dispositivos/redes variados. No se prueban aquí despliegues multiusuario ni integración bancaria. El resultado de seis clips no acredita las metas del entregable 2 ni seguridad para autorizar transferencias reales.

## Actualización v3: monitoreo en vivo (25 de octubre de 2026)

`python -m pytest -q --run-model`: **31 pruebas aprobadas**. Cubren sesiones en vivo con consentimiento, rechazo de cuadros inválidos, alerta, bloqueo, el ataque que empieza a mitad de la llamada (decide la ventana reciente), autorización de un interlocutor real solo con evidencia suficiente, reglas de resolución (canal alterno, rol de seguridad, segregación, SLA), resolución única, cadena de hashes y detección de alteración, migración de la tabla v2 e inferencia real sobre cuadros públicos.

`scripts/browser_smoke.py` en Chrome: llamada simulada con deepfake (alerta → bloqueo → intento de liberación por el analista rechazado por la regla → rechazo por seguridad), cámara falsa sin rostro (sin autorización), modo de grabación completo, bitácora íntegra y vista móvil.

Medición en vivo a 2 cuadros/s sobre los clips completos: originales 04 y 05 → autorizar (19); original 01 → verificar (35); manipulados 01 → verificar (70; ≥ 75 durante la alerta, lo que produce bloqueo), 05 → verificar (60) y **04 → autorizar (22): falso negativo**. No se probó con webcam ni con una llamada real de Zoom en este equipo.
