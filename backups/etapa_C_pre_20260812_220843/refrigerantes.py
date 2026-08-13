from __future__ import annotations

PSI_PARA_PA = 6894.757293168
PRESSAO_ATMOSFERICA_PSI = 14.6959

REFRIGERANTES = {
    "R404A": "R404A",
    "R410A": "R410A",
    "R407C": "R407C",
    "R507A": "R507A",
    "R134a": "R134a",
    "R22": "R22",
    "R32": "R32",
}


def coolprop_disponivel() -> bool:
    try:
        from CoolProp.CoolProp import PropsSI  # noqa: F401
        return True
    except ImportError:
        return False


def _pressao_absoluta_pa(pressao_psig: float) -> float:
    pressao_absoluta_psi = max(
        0.01,
        pressao_psig + PRESSAO_ATMOSFERICA_PSI,
    )
    return pressao_absoluta_psi * PSI_PARA_PA


def temperatura_saturacao_c(
    pressao_psig: float,
    refrigerante: str,
    qualidade: int,
) -> float | None:
    """
    Converte pressão manométrica (PSIG) em temperatura de saturação (°C).

    qualidade=1: temperatura de orvalho, usada no superaquecimento.
    qualidade=0: temperatura de bolha, usada no sub-resfriamento.
    """
    nome_coolprop = REFRIGERANTES.get(refrigerante)

    if nome_coolprop is None:
        return None

    try:
        from CoolProp.CoolProp import PropsSI

        temperatura_k = PropsSI(
            "T",
            "P",
            _pressao_absoluta_pa(pressao_psig),
            "Q",
            qualidade,
            nome_coolprop,
        )

        return float(temperatura_k - 273.15)

    except (ImportError, TypeError, ValueError, RuntimeError, OverflowError):
        return None


def calcular_superaquecimento_c(
    pressao_succao_psig: float,
    temperatura_linha_succao_c: float,
    refrigerante: str,
) -> tuple[float | None, float | None]:
    temperatura_saturacao = temperatura_saturacao_c(
        pressao_succao_psig,
        refrigerante,
        qualidade=1,
    )

    if temperatura_saturacao is None:
        return None, None

    superaquecimento = (
        temperatura_linha_succao_c
        - temperatura_saturacao
    )

    return superaquecimento, temperatura_saturacao


def calcular_subresfriamento_c(
    pressao_condensacao_psig: float,
    temperatura_linha_liquido_c: float,
    refrigerante: str,
) -> tuple[float | None, float | None]:
    temperatura_saturacao = temperatura_saturacao_c(
        pressao_condensacao_psig,
        refrigerante,
        qualidade=0,
    )

    if temperatura_saturacao is None:
        return None, None

    subresfriamento = (
        temperatura_saturacao
        - temperatura_linha_liquido_c
    )

    return subresfriamento, temperatura_saturacao