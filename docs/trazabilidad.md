# Trazabilidad académica — versión 2

Los umbrales académicos provienen del entregable 2. Los pesos, la arquitectura y el tratamiento de incertidumbre son recomendaciones técnicas del prototipo, no exigencias inventadas del curso.

| Fuente y requisito | Evidencia implementada | Qué falta |
|---|---|---|
| Entregable 1: transferencia solicitada por videollamada | Formulario, video, recomendación de tesorería | Integración en llamada en vivo y sistema de pagos. |
| Entregable 1: analizar señales de manipulación | YuNet + ViT sobre recortes; `detector.py`, `pipeline.py` | Audio, sincronía, identidad y validación en ataques representativos. |
| Entregable 2: puntaje 0–100, rangos 0–30, 31–70 y 71–100 | `decision.py`, razones y trazabilidad | Calibrar pesos y umbrales con costos y evidencia real. |
| Entregable 2: cuenta nueva y monto mayor al límite obliga revisión | Reglas independientes del detector; pruebas automáticas | Contrastar los campos con ERP y políticas del cliente. |
| Entregable 2: no autorizar sin evidencia suficiente | Ausencia de rostro, incertidumbre, calidad o falta de verificación alterna impiden recomendar autorización | Verificación independiente comprobable y autenticación de analistas. |
| Entregable 2: no decidir sin registro | SQLite transaccional antes de publicar resultado; pruebas de fallo de bitácora | Acceso por roles, cifrado/retención, protección contra modificación administrativa. |
| Entregable 2: cinco métricas de aceptabilidad | Seis muestras públicas evaluadas con todas sus salidas y un falso negativo visible | Las metas de fraude detenido, fricción, tiempos, equidad y trazabilidad operativa no se han demostrado. |
| PDF p. 16: flujo, 3–5 datos críticos, calidad y trazabilidad | Manifiesto de fuentes/hashes; versión del modelo y reglas; tabla siguiente y diagrama en alcance | Redactar y justificar avance de sesión 3 en máximo 2 páginas. |
| PDF p. 17: tres riesgos, controles, triggers, autoridad y supervisión | Matriz preliminar siguiente, cola limitada, validación y revisión | Acordar responsables, reglas de suspensión y liberación; redactar sesión 4 en máximo 2 páginas. |
| PDF pp. 9 y 11: escrito final y sustentación | Demo reproducible, exportación y documentación | Documento máximo 10 páginas y defensa; fecha del escrito: 11 de noviembre de 2026, según pp. 2 y 13. |

## Cinco datos críticos para el avance 3

| Dato | Origen / transformación | Calidad y trazabilidad |
|---|---|---|
| Video | Muestra pública autorizada o carga local; 24 instantes y recortes temporales | Extensión y decodificación, tamaño/duración, hash; no se retiene el archivo subido. |
| Señal del modelo | Pesos y revisión fijados; salida por rostro y media de máximos por instante | Modelo local verificado, cobertura facial, dispersión, zona incierta y versión del pipeline. |
| Monto y límite | Declaración del operador, comparación decimal | Positivos, finitos, dos decimales; deben contrastarse con ERP en un piloto. |
| Cuenta del beneficiario | Declaración de cuenta nueva | Regla de revisión obligatoria; no existe historial bancario conectado. |
| Autorización y verificación alterna | Declaraciones del operador | Se exige autorización para analizar y se registra; la verificación no se comprueba externamente. |

## Matriz preliminar de riesgo y control para el avance 4

| Riesgo | Evidencia / disparador | Control actual | Responsable propuesto |
|---|---|---|---|
| Suplantación omitida o falsa alarma | El ejemplo `fake_04` produce un falso negativo; señales intermedias son inciertas | Mostrar límites y motivos; revisión humana y canal alterno; no usar el modelo como comprobación de identidad | Seguridad evalúa el detector; tesorería verifica la solicitud. |
| Datos o inferencia no confiables | Video inválido, sin rostros, monto inválido, modelo ausente o hash diferente | Rechazo o resultado inconcluso; sin predicción simulada de respaldo | Responsable de datos y operación técnica. |
| Uso indebido de datos o pérdida de trazabilidad | Falta de autorización, fallo de almacenamiento, exposición de imágenes | Entrada con autorización declarada, eliminación temporal, bitácora sin imágenes, fallo cerrado al no poder registrar | Privacidad y seguridad, pendientes de designación formal. |

La asignación anterior es una propuesta para discusión, no un esquema de autoridad ya aprobado. El prototipo no implementa un proceso de liberación de bloqueos ni permisos por rol. Antes de una prueba organizacional deben definirse autenticación, evidencia de verificación alterna, quién puede suspender el modelo y quién responde ante errores.

Los resultados de seis ejemplos apoyan la explicación del sistema y sus límites. No constituyen validación independiente ni justifican afirmar que se cumple el 98 % de fraude detenido o las demás metas del entregable 2.
