# Ampliación v2: detección visual con un modelo entrenado

Solicitud del usuario: incorporar detección de deepfakes y videos públicos con personas. Este documento actualiza el alcance inicial del prototipo.

## Diseño y criterios antes de implementar

- Modelo candidato: `prithivMLmods/Deep-Fake-Detector-v2-Model`, Vision Transformer con pesos entrenados y licencia Apache-2.0. Fuente: https://huggingface.co/prithivMLmods/Deep-Fake-Detector-v2-Model . Inferencia local sobre rostros extraídos de cuadros del video, sin ejecutar código remoto del modelo. Pesos Safetensors y revisión fija.
- Muestras: archivos originales 1, 4 y 5 y versiones manipuladas de `ud-biometrics/deepfake-dataset`. Fuente: https://huggingface.co/datasets/ud-biometrics/deepfake-dataset . Licencia declarada por el editor: CC BY-NC-ND 4.0. Se descargan para uso académico sin alterar sus bytes; no se incluyen en Git. Los IDs se eligieron antes de observar las predicciones, por tamaño de descarga.
- Flujo: validar archivo → muestrear instantes uniformemente → localizar rostros → clasificar recortes → agregar resultados → aplicar reglas de transferencia → registrar auditoría. Las etiquetas de referencia del dataset nunca son entradas del clasificador.
- Robustez: límites de tamaño/duración, errores legibles, análisis en segundo plano, estado de progreso, resultados inconclusos si faltan rostros/evidencia, bitácora transaccional y exportación de resultados.
- Interfaz: reproducción del video, ejemplos reales/manipulados, resultados por cuadro y motivos de la decisión. La confianza del modelo y el puntaje de la transferencia se muestran por separado.
- Aceptación: las muestras se descargan con hash verificado, el modelo hace inferencia real sobre sus píxeles, la evaluación registra aciertos y errores de las seis muestras, y los casos inválidos o sin rostro no producen una falsa confirmación de autenticidad.

El modelo es un clasificador de imágenes aplicado a cuadros de video; no analiza audio ni sincronía labial. Sus cifras publicadas sobre imágenes no constituyen exactitud de VeriCall en videos. Los umbrales de revisión son provisionales y el conjunto de seis ejemplos es una demostración, no una validación de producción.

La clase binaria usa 0,5, equivalente a escoger la clase con mayor salida softmax en el ejemplo del autor. Además se conserva una zona de incertidumbre de 0,25 a 0,75: una predicción binaria «deepfake» puede tener evidencia moderada y requerir revisión. No se ajustan los umbrales para conseguir que los ejemplos coincidan con su etiqueta. Un puntaje bajo tampoco acredita identidad.
