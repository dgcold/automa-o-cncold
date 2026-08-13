def limitar(
    valor: float,
    minimo: float,
    maximo: float,
) -> float:
    return max(minimo, min(maximo, valor))


def converter_para_0_10v(
    valor: float,
    minimo_engenharia: float,
    maximo_engenharia: float,
) -> float:
    valor = limitar(
        valor,
        minimo_engenharia,
        maximo_engenharia,
    )

    proporcao = (
        (valor - minimo_engenharia)
        / (maximo_engenharia - minimo_engenharia)
    )

    return proporcao * 10.0


def converter_para_4_20ma(
    valor: float,
    minimo_engenharia: float,
    maximo_engenharia: float,
) -> float:
    valor = limitar(
        valor,
        minimo_engenharia,
        maximo_engenharia,
    )

    proporcao = (
        (valor - minimo_engenharia)
        / (maximo_engenharia - minimo_engenharia)
    )

    return 4.0 + proporcao * 16.0


def converter_para_registrador(
    valor_eletrico: float,
    tipo_saida: str,
) -> int:
    tipo = tipo_saida.upper().replace(" ", "")

    if tipo == "0-10V":
        valor_eletrico = limitar(
            valor_eletrico,
            0.0,
            10.0,
        )

        return round(
            valor_eletrico / 10.0 * 10000
        )

    if tipo == "4-20MA":
        valor_eletrico = limitar(
            valor_eletrico,
            4.0,
            20.0,
        )

        return round(
            (valor_eletrico - 4.0)
            / 16.0
            * 10000
        )

    raise ValueError(
        f"Tipo de saída inválido: {tipo_saida}"
    )


def calcular_saida_canal(canal) -> tuple[float, int]:
    if canal.tipo_saida.upper() == "0-10V":
        valor_eletrico = converter_para_0_10v(
            canal.valor,
            canal.minimo,
            canal.maximo,
        )

    elif canal.tipo_saida.upper() == "4-20MA":
        valor_eletrico = converter_para_4_20ma(
            canal.valor,
            canal.minimo,
            canal.maximo,
        )

    else:
        raise ValueError(
            f"Saída não reconhecida no CH{canal.numero}: "
            f"{canal.tipo_saida}"
        )

    registrador = converter_para_registrador(
        valor_eletrico,
        canal.tipo_saida,
    )

    return valor_eletrico, registrador