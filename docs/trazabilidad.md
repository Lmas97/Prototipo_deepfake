# Trazabilidad entre entregables y prototipo

| Fuente y requisito | Componente o evidencia en el repositorio | Estado y límite |
|---|---|---|
| Entregable 1: decisión sobre transferencia pedida por videollamada | `vericall/app.py`, formulario y casos | Solicitud ficticia fuera de línea; no hay llamada ni pago real. |
| Entregable 1: video, audio, biometría, historial y contexto técnico | `vericall/video.py` y campos de transacción | Solo se decodifica video y se ingresan monto/límite/beneficiario; audio, identidad, historial y conexión siguen pendientes. |
| Entregable 1: humano confirma, alto riesgo se bloquea | `vericall/decision.py`, acciones y explicación | Las acciones son recomendaciones locales. No existe integración bancaria. |
| Entregable 2: puntaje 0–100 y rangos 0–30, 31–70, 71–100 | `vericall/decision.py` | Rangos implementados; pesos heurísticos recomendados por el prototipo, sin calibración académica. |
| Entregable 2: cuenta nueva o monto superior al límite obliga revisión | `vericall/decision.py` | Implementado incluso si el puntaje es bajo. |
| Entregable 2: consentimiento y registro obligatorio | `vericall/app.py`, `vericall/audit.py` | Se exige declaración de consentimiento y se registra toda decisión válida; no verifica jurídicamente el consentimiento. |
| Entregable 2: fraude detenido ≥98 %, bloqueos falsos ≤2 %, liberación ≤15 min, trazabilidad 100 %, brecha ≤1 punto | `docs/proyecto_y_alcance.md` | Metas documentadas. No evaluables con estas figuras sintéticas ni con casos sin etiquetas reales. |
| PDF p. 16, sesión 3: flujo, datos críticos y calidad | Diagrama y tabla abajo; `vericall/video.py`, `tests/test_prototype.py` | Base para redactar avance de máximo 2 páginas. Requiere completar fuentes reales, responsables y análisis de sesgos. |
| PDF p. 16, sesión 3: trazabilidad y vacíos | JSONL con versión de reglas, hash, entradas, métricas y motivos; preguntas abiertas | Permite reconstruir cálculo local. No demuestra procedencia de una llamada real. |
| PDF p. 17, sesión 4: riesgos, controles, triggers, autoridad | Matrices preliminares abajo | Base para discusión del equipo; probabilidad, severidad y responsabilidades definitivas siguen por acordar. |
| PDF pp. 9, 11: escrito final y sustentación | `docs/proyecto_y_alcance.md`, esta matriz y demo local | Insumos, no entregables académicos completos. |

## Datos críticos del MVP (base para sesión 3)

| Dato | Fuente y transformación | Validación / consecuencia si falla |
|---|---|---|
| Video | Archivo sintético incluido o archivo temporal cargado; decodificación y muestreo de cuadros | AVI/MP4, ≤25 MB, duración y resolución acotadas. Video inválido impide decidir. No se comprueba identidad. |
| Monto y límite | Operador / caso de muestra; comparación decimal | Deben ser positivos y finitos. Si están errados, se omite o dispara revisión equivocadamente. |
| Beneficiario nuevo | Operador / caso de muestra; regla de revisión | Declaración manual no contrastada con ERP. Error puede dejar pasar un cambio de cuenta. |
| Verificación alterna | Declaración del operador; puerta para recomendación de autorizar | No hay prueba externa de la llamada. Una declaración falsa podría producir autorización indebida. |
| Consentimiento | Declaración del operador antes de decodificar | Sin declaración se rechaza. No hay registro de identidad, alcance ni vigencia de una autorización real. |

## Matriz preliminar para sesión 4

| Riesgo prioritario | Señal y control en el MVP | Responsable propuesto / falta definir |
|---|---|---|
| Suplantación no detectada | No se presenta el puntaje como detector; verificación independiente declarada y confirmación humana | Tesorería ejecuta verificación; seguridad define canal y evidencia. Asignación definitiva pendiente. |
| Datos de transacción o llamada incorrectos | Validación de tipo, monto y video; cuenta nueva y exceso de límite fuerzan revisión | Tesorería valida contra ERP; gobierno de datos define calidad y linaje. Integración pendiente. |
| Tratamiento indebido de biometría / pérdida de evidencia | Consentimiento declarado, video temporal, hash y bitácora de razones | Responsable de privacidad y seguridad por designar; política de acceso/retención pendiente. |

**Disparadores propuestos:** video inválido o falta de consentimiento detiene evaluación; puntaje ≥71 bloquea y escala; cuenta nueva o monto alto obliga revisión; bitácora no disponible debe impedir emitir una decisión válida (la app devuelve error de servidor, por lo que este fallo debe manejarse mejor antes de uso real). La autoridad para suspender reglas, investigar errores y liberar bloqueos debe definirse en el avance 4; el código no la implementa.

Para el escrito final faltan evidencia empírica de desempeño y equidad, modelo de responsabilidades, política aprobada de gobierno de datos, descripción de integración real y referencias externas verificadas. Los entregables existentes tienen umbrales preliminares, no métricas ya alcanzadas.
