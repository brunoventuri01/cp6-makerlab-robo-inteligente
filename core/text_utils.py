"""
Utilidades de texto compartilhadas por todo o projeto.

O reconhecimento de fala (STT) devolve texto "sujo": com acentos, pontuação,
letras maiúsculas e variações de grafia. Antes de comparar qualquer coisa
(wake word, regex das skills) normalizamos tudo aqui, em um lugar só.
"""

import re
import unicodedata

# Números por extenso em pt-BR. Usado pela CalculatorSkill para aceitar
# "dois mais três" além de "2 + 3".
UNIDADES = {
    "zero": 0, "um": 1, "uma": 1, "dois": 2, "duas": 2, "tres": 3,
    "quatro": 4, "cinco": 5, "seis": 6, "sete": 7, "oito": 8, "nove": 9,
    "dez": 10, "onze": 11, "doze": 12, "treze": 13, "catorze": 14,
    "quatorze": 14, "quinze": 15, "dezesseis": 16, "dezessete": 17,
    "dezoito": 18, "dezenove": 19,
}
DEZENAS = {
    "vinte": 20, "trinta": 30, "quarenta": 40, "cinquenta": 50,
    "sessenta": 60, "setenta": 70, "oitenta": 80, "noventa": 90,
}
CENTENAS = {
    "cem": 100, "cento": 100, "duzentos": 200, "trezentos": 300,
    "quatrocentos": 400, "quinhentos": 500, "seiscentos": 600,
    "setecentos": 700, "oitocentos": 800, "novecentos": 900,
}


def remover_acentos(texto: str) -> str:
    """Converte "três" -> "tres" usando decomposição unicode (NFD)."""
    decomposto = unicodedata.normalize("NFD", texto)
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn")


def normalizar(texto: str) -> str:
    """
    Deixa o texto em um formato canônico para comparação:
    minúsculas, sem acento, sem pontuação e sem espaços duplicados.

    >>> normalizar("Roberto, que HORAS são?")
    'roberto que horas sao'
    """
    if not texto:
        return ""
    texto = remover_acentos(texto.lower())
    # "12-8" é subtração, não hífen de palavra composta: preserva o sentido.
    texto = re.sub(r"(?<=\d)\s*-\s*(?=\d)", " menos ", texto)
    # Agora sim: hífen vira espaço ("sexta-feira" -> "sexta feira").
    texto = texto.replace("-", " ")
    # A vírgula só sobrevive entre dígitos (decimal "3,5"); nos demais casos some.
    texto = re.sub(r"(?<=\d),(?=\d)", ".", texto)
    # Mantemos os símbolos matemáticos para a calculadora entender "12 + 8".
    texto = re.sub(r"[^\w\s./+*%]", " ", texto)
    return re.sub(r"\s+", " ", texto).strip()


def palavras_para_numero(tokens: list) -> int:
    """
    Converte uma sequência de palavras em um inteiro.
    Ex.: ["cento", "e", "vinte", "e", "tres"] -> 123
    Lança ValueError se algum token não for reconhecido.
    """
    total = 0
    encontrou = False
    for token in tokens:
        if token == "e":  # conectivo do português: "cento e vinte"
            continue
        if token in CENTENAS:
            total += CENTENAS[token]
        elif token in DEZENAS:
            total += DEZENAS[token]
        elif token in UNIDADES:
            total += UNIDADES[token]
        elif token in ("mil",):
            total = (total or 1) * 1000
        else:
            raise ValueError(f"token numérico desconhecido: {token}")
        encontrou = True
    if not encontrou:
        raise ValueError("nenhum número encontrado")
    return total


def substituir_numeros_por_extenso(texto: str) -> str:
    """
    Percorre o texto trocando blocos de números por extenso pelo dígito.
    "dois mais cento e vinte" -> "2 mais 120"
    """
    tokens = texto.split()
    saida = []
    buffer = []

    def descarregar():
        """Converte o que estiver acumulado no buffer e joga na saída."""
        if not buffer:
            return
        try:
            saida.append(str(palavras_para_numero(buffer)))
        except ValueError:
            saida.extend(buffer)  # não era número: devolve as palavras originais
        buffer.clear()

    numericas = set(UNIDADES) | set(DEZENAS) | set(CENTENAS) | {"mil"}
    for i, token in enumerate(tokens):
        # "e" só entra no buffer se estiver ligando dois números ("vinte e um")
        eh_conectivo = token == "e" and buffer and i + 1 < len(tokens) and tokens[i + 1] in numericas
        if token in numericas or eh_conectivo:
            buffer.append(token)
        else:
            descarregar()
            saida.append(token)
    descarregar()
    return " ".join(saida)
