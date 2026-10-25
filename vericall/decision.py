"""Reglas transparentes y provisionales de riesgo de transferencia."""

from decimal import Decimal, InvalidOperation


RULE_VERSION = "risk-v2.0"


class InputError(ValueError):
    pass


def positive_money(raw: object, label: str) -> Decimal:
    try:
        number = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise InputError(f"{label} debe ser un número positivo.") from None
    if not number.is_finite() or number <= 0 or number > Decimal("1000000000000"):
        raise InputError(f"{label} debe ser un número positivo y finito de hasta 10¹².")
    if number.as_tuple().exponent < -2:
        raise InputError(f"{label} admite como máximo dos decimales.")
    return number.quantize(Decimal("0.01"))


def evaluate(*, amount: object, limit: object, new_beneficiary: bool,
             alternate_verified: bool, detection: dict) -> dict:
    amount_value = positive_money(amount, "El monto")
    limit_value = positive_money(limit, "El límite")
    reasons = []
    score = 0

    def add(points: int, code: str, explanation: str):
        nonlocal score
        score += points
        reasons.append({"code": code, "points": points, "text": explanation})

    model_score = detection["fake_score"] if detection["sufficient_face_evidence"] else None
    if model_score is not None:
        add(round(model_score * 100), "visual_model", "Señal de manipulación facial del modelo entrenado.")
    if new_beneficiary:
        add(25, "new_beneficiary", "Beneficiario nuevo: requiere revisión por regla del proyecto.")
    if amount_value > limit_value:
        add(25, "over_limit", "Monto superior al límite del cliente: requiere revisión.")
    quality_problem = False
    if detection["quality"]["frozen_transition_ratio"] >= 0.8:
        quality_problem = True
        add(10, "frozen_video", "La imagen permanece casi inmóvil: se requiere revisión de la evidencia.")
    if detection["quality"]["dark_frame_ratio"] >= 0.5:
        quality_problem = True
        add(10, "dark_video", "La mayoría de cuadros analizados son demasiado oscuros.")
    if not detection["sufficient_face_evidence"]:
        reasons.append({"code": "insufficient_faces", "points": 0,
                        "text": "No hay suficientes rostros observables para concluir sobre el video."})
    elif detection["verdict"] == "inconclusive":
        reasons.append({"code": "uncertain_model", "points": 0,
                        "text": "La salida del modelo está en la zona de incertidumbre."})
    if detection["multiple_faces"]:
        reasons.append({"code": "multiple_faces", "points": 0,
                        "text": "Aparecen varios rostros; no se ha vinculado la identidad del solicitante."})

    score = min(score, 100)
    mandatory_review = (new_beneficiary or amount_value > limit_value or quality_problem
                        or detection["verdict"] == "inconclusive" or detection["multiple_faces"])
    if score >= 71:
        action = "bloquear_y_escalar"
    elif score >= 31 or mandatory_review or not alternate_verified:
        action = "revisar_canal_alterno"
    else:
        action = "autorizar_pendiente_confirmacion"

    if not alternate_verified:
        reasons.append({"code": "no_alternate_verification", "points": 0,
                        "text": "No consta verificación independiente; no se recomienda autorizar."})
    if not reasons:
        reasons.append({"code": "no_flags", "points": 0,
                        "text": "Sin alertas en las reglas de esta demostración; el analista debe confirmar."})

    return {
        "rule_version": RULE_VERSION,
        "score": score,
        "action": action,
        "reasons": reasons,
        "inputs": {
            "amount": str(amount_value),
            "limit": str(limit_value),
            "new_beneficiary": new_beneficiary,
            "alternate_verified_declared": alternate_verified,
        },
        "warning": "El puntaje combina la señal visual y reglas de negocio. No es una probabilidad de fraude ni ejecuta un pago.",
    }
