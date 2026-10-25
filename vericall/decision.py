"""Reglas transparentes y provisionales de riesgo de transferencia."""

from decimal import Decimal, InvalidOperation


RULE_VERSION = "mvp-1"


class InputError(ValueError):
    pass


def positive_money(raw: object, label: str) -> Decimal:
    try:
        number = Decimal(str(raw))
    except (InvalidOperation, TypeError):
        raise InputError(f"{label} debe ser un número positivo.") from None
    if not number.is_finite() or number <= 0 or number > Decimal("1000000000000"):
        raise InputError(f"{label} debe ser un número positivo y finito menor a 10¹².")
    return number


def evaluate(*, amount: object, limit: object, new_beneficiary: bool,
             alternate_verified: bool, video_metrics: dict) -> dict:
    amount_value = positive_money(amount, "El monto")
    limit_value = positive_money(limit, "El límite")
    reasons = []
    score = 0

    def add(points: int, code: str, explanation: str):
        nonlocal score
        score += points
        reasons.append({"code": code, "points": points, "text": explanation})

    if new_beneficiary:
        add(25, "new_beneficiary", "Beneficiario nuevo: requiere revisión por regla del proyecto.")
    if amount_value > limit_value:
        add(25, "over_limit", "Monto superior al límite del cliente: requiere revisión.")
    if video_metrics["frozen_transition_ratio"] >= 0.8:
        add(30, "frozen_video", "El video presenta muchos cuadros casi idénticos; calidad insuficiente.")
    if video_metrics["dark_frame_ratio"] >= 0.5:
        add(25, "dark_video", "La mayoría de cuadros muestreados son muy oscuros.")
    if video_metrics["duration_seconds"] < 2:
        add(20, "short_video", "La muestra dura menos de dos segundos.")
    if video_metrics["width"] < 160 or video_metrics["height"] < 120:
        add(20, "low_resolution", "La resolución está por debajo del mínimo del prototipo.")

    score = min(score, 100)
    mandatory_review = new_beneficiary or amount_value > limit_value
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
        "video_metrics": video_metrics,
        "warning": "Reglas heurísticas sin validación: no detectan deepfakes ni autorizan pagos reales.",
    }
