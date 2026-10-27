"""
Contrato que TODA habilidade da Roberto obedece.

Essa é a espinha dorsal da orientação a objetos do projeto: a classe Roberto
recebe uma lista de Skills no construtor e não conhece nenhuma delas por
dentro. Para adicionar um comando novo basta criar uma subclasse de Skill e
registrá-la no main.py — nada mais no núcleo muda.
"""

import re
from abc import ABC, abstractmethod

from core.text_utils import normalizar


class Contexto:
    """
    Objeto que a Roberto passa para as skills durante a execução.

    Serve para dois propósitos:
    - dar acesso controlado a recursos compartilhados (falar, LLM, caminhos);
    - permitir que uma skill peça uma resposta ao usuário (diálogo multi-turno),
      registrando um callback com aguardar_resposta().
    """

    def __init__(self, assistente, speaker, llm, caminhos: dict):
        self.assistente = assistente
        self.speaker = speaker
        self.llm = llm
        self.caminhos = caminhos          # {"agenda": ..., "modelo_faces": ...}
        self._callback_pendente = None    # função que trata a próxima fala

    def falar(self, texto: str) -> None:
        """Fala algo no meio da execução, sem esperar o retorno da skill."""
        self.speaker.falar(texto)

    def aguardar_resposta(self, callback) -> None:
        """
        Registra quem vai tratar a PRÓXIMA fala do usuário.

        É assim que o item 2 ("Ok, qual evento devo cadastrar?") funciona: a
        AgendaSkill devolve a pergunta e registra um callback; a Roberto entra
        no estado AGUARDANDO_RESPOSTA e entrega a fala seguinte direto para
        esse callback, sem exigir a wake word (decisão documentada no README).
        """
        self._callback_pendente = callback

    def consumir_callback(self):
        """A Roberto chama isto para pegar (e limpar) o callback registrado."""
        callback, self._callback_pendente = self._callback_pendente, None
        return callback

    @property
    def tem_pendencia(self) -> bool:
        return self._callback_pendente is not None


class Skill(ABC):
    """
    Classe abstrata base de todas as habilidades.

    Atributos de classe que as subclasses preenchem:
      nome      -> identificador curto, usado em logs e no function calling
      descricao -> frase que explica a skill para o LLM
      padroes   -> lista de regex (já normalizadas) que disparam a skill
    """

    nome = "skill"
    descricao = ""
    padroes = []

    def __init__(self):
        # Compila as regex uma única vez, no boot, e não a cada fala.
        self._regex = [re.compile(p) for p in self.padroes]

    def matches(self, texto_normalizado: str) -> bool:
        """True se alguma regex da skill casar com a fala já normalizada."""
        return any(r.search(texto_normalizado) for r in self._regex)

    @abstractmethod
    def execute(self, texto: str, ctx: Contexto) -> str:
        """Executa a habilidade e devolve o que a Roberto deve falar."""

    # --- Integração com function calling (fallback inteligente do router) ---
    def ferramentas(self) -> list:
        """
        Descreve a skill no formato de 'tools' da OpenAI. Retornar [] deixa a
        skill fora do fallback por LLM (só regex).
        """
        return []

    def executar_ferramenta(self, nome: str, argumentos: dict, ctx: Contexto) -> str:
        """Executa a skill a partir dos argumentos estruturados do LLM."""
        raise NotImplementedError(f"{self.nome} não implementa a ferramenta {nome}")

    # --- Auxiliares ---
    @staticmethod
    def normalizar_texto(texto: str) -> str:
        """Atalho para a normalização usada nas comparações internas."""
        return normalizar(texto)

    def remover_gatilho(self, texto: str) -> str:
        """
        Devolve o que sobra da fala depois do gatilho.
        Ex.: "calcular dois mais dois" -> "dois mais dois"
        """
        normalizado = normalizar(texto)
        for regex in self._regex:
            achado = regex.search(normalizado)
            if achado:
                return normalizado[achado.end():].strip(" ,.")
        return normalizado
