"""Reglas transparentes y provisionales de riesgo de transferencia."""

from datetime import datetime
from decimal import Decimal, InvalidOperation

from vericall.config import RESOLUTION_SLA_SECONDS

RULE_VERSION = "risk-v3.0"
ROLES = {"analista": "Analista de tesorería", "seguridad": "Área de seguridad"}


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


def evaluate(*, amount: object, limit: object, new_beneficiary: bool, detection: dict) -> dict:
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
    # Rangos del entregable 2: 0–30 aceptar, 31–70 revisar, 71–100 bloquear.
    if score >= 71:
        action = "bloquear_y_escalar"
    elif score >= 31 or mandatory_review:
        action = "revisar_canal_alterno"
    else:
        action = "autorizar_pendiente_confirmacion"

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
        },
        "warning": "El puntaje combina la señal visual y reglas de negocio. No es una probabilidad de fraude ni ejecuta un pago.",
    }


def resolve(entry: dict, *, outcome: str, role: str, actor: str, alternate_verified: bool,
            channel: str, now: datetime) -> dict:
    """Decisión humana final. Aplica las restricciones innegociables del entregable 2."""
    action = entry["decision"]["action"]
    actor, channel = (actor or "").strip()[:80], (channel or "").strip()[:200]
    if outcome not in ("release", "reject"):
        raise InputError("Elige liberar o rechazar el pago.")
    if role not in ROLES:
        raise InputError("Rol no reconocido.")
    if not actor:
        raise InputError("Indica el nombre de quien toma la decisión final.")
    if alternate_verified and not channel:
        raise InputError("Describe el canal alterno usado, por ejemplo: llamada al número registrado del directivo.")
    if outcome == "release":
        if action == "revisar_canal_alterno" and not alternate_verified:
            raise InputError("Este pago solo puede liberarse después de verificarlo por un canal alterno.")
        if action == "bloquear_y_escalar":
            if role != "seguridad":
                raise InputError("Un bloqueo crítico solo puede liberarlo el área de seguridad.")
            if not alternate_verified:
                raise InputError("Nunca se libera un bloqueo crítico sin verificación por canal alterno.")
            if actor.casefold() == (entry.get("analyst") or "").strip().casefold():
                raise InputError("Segregación de funciones: quien solicitó la evaluación no puede liberar su propio bloqueo.")
    elapsed = (now - datetime.fromisoformat(entry["timestamp_utc"])).total_seconds()
    return {
        "outcome": outcome,
        "status": "liberada" if outcome == "release" else "rechazada",
        "role": role, "role_label": ROLES[role], "actor": actor,
        "alternate_verified": alternate_verified, "alternate_channel": channel or None,
        "recommended_action": action,
        "elapsed_seconds": round(elapsed, 1),
        "sla_seconds": RESOLUTION_SLA_SECONDS,
        "within_sla": elapsed <= RESOLUTION_SLA_SECONDS,
        "rule_version": RULE_VERSION,
        "note": "Rol declarado en la demostración; un piloto requiere autenticación y permisos por rol.",
    }
