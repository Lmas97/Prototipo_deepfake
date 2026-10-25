# Material de prueba y atribución

## Videos públicos con personas

**Editor:** Unidata, cuenta `ud-biometrics`. **Fuente primaria:** https://huggingface.co/datasets/ud-biometrics/deepfake-dataset . **Licencia publicada por el editor:** Creative Commons Attribution-NonCommercial-NoDerivatives 4.0 (CC BY-NC-ND 4.0), https://creativecommons.org/licenses/by-nc-nd/4.0/ . Los archivos se usan en esta demostración académica sin alterar su contenido. La etiqueta «real»/«fake» es la referencia del editor, no una comprobación independiente de identidad.

Revisión fijada: `9252c30f344f38267cc1faf99542ce457afcca67`. El manifiesto `config/assets.json` incluye URL de descarga y SHA-256 de cada archivo. Se obtienen desde el editor con `python scripts/download_assets.py --only samples`. No se redistribuyen en Git.

| Nombre local | Archivo en la fuente | Referencia |
|---|---|---|
| public/real_01.mp4 | video/1.mp4 | Original |
| public/fake_01.mp4 | deepfake/1.mp4 | Rostro sustituido |
| public/real_04.mp4 | video/4.mp4 | Original |
| public/fake_04.mp4 | deepfake/4.mp4 | Rostro sustituido |
| public/real_05.mov | video/5.MOV | Original |
| public/fake_05.mov | deepfake/5.mov | Rostro sustituido |

Se eligieron estos tres IDs por tamaño antes de ejecutar el clasificador, y se publican todos sus resultados. La descripción del editor cita aisaver.io, faceswapvideo.ai y magichour.ai como generadores del dataset; no se asigna un generador específico a un clip porque la ficha no lo establece por archivo. En la versión evaluada, `fake_04` pasa inadvertido para el modelo y se conserva expresamente como ejemplo de limitación.

Los enlaces de la ficha a un dataset comercial más grande no son necesarios: esta app usa solo seis archivos de su muestra pública y no compra ni solicita datos adicionales.

## Fixtures sintéticos propios

`videos/moving_shapes.avi` y `videos/frozen_shapes.avi` fueron generados por `generate_videos.py` y no contienen personas. Sirven para comprobar que el detector devuelve evidencia insuficiente cuando no hay rostro. No son ejemplos de deepfake. `invalid/not_a_video.txt` comprueba el rechazo de formato. También se prueba texto renombrado como `.mp4` para verificar que la extensión no reemplaza la decodificación.

El manifiesto `cases.json` describe únicamente estas pruebas negativas; la interfaz utiliza los videos públicos declarados en `config/assets.json`.
