"""
Orquestrador: a classe Roberto e o portão da wake word.

Fluxo do loop principal (exatamente o que o item 1 do enunciado pede):

    escuta -> transcreve -> começa com a wake word?
       ├─ não  -> imprime o texto na tela e volta (nenhuma ação)
       └─ sim  -> remove a wake word -> router.route(comando)
                    ├─ alguma skill deu match -> executa -> fala a resposta
                    └─ nenhuma                -> IA generativa (item 9)
"""

from enum import Enum
import re

from core.text_utils import normalizar
from skills.base import Contexto


class Estado(Enum):
    """Máquina de estados da assistente."""

    OCIOSO = "ocioso"                         # esperando a wake word
    EXECUTANDO = "executando"                 # rodando uma skill
    AGUARDANDO_RESPOSTA = "aguardando"        # diálogo aberto (item 2)


class WakeWordGate:
    """
    Portão de entrada: só deixa passar falas que comecem com o nome da
    assistente.

    Armadilha real: "Roberto" não é palavra do português, então o STT erra muito.
    Dependendo do sotaque e do microfone, o Google devolve "nexo", "next",
    "lexus", "néxus"... Por isso comparamos o texto já normalizado (sem acento,
    sem pontuação) contra uma lista de variantes aceitas.

    Se na sua máquina ele insistir em transcrever de outro jeito, basta somar a
    grafia nova a esta lista — é o ajuste mais provável antes da apresentação.
    """

    # Nao aceitar palavras apenas parecidas com o nome: reduz falsos disparos.
    VARIANTES_PADRAO = []

    # Únicas palavras toleradas ANTES do nome. Qualquer outra coisa na frente
    # significa que a assistente não estava sendo chamada de fato.
    PREENCHIMENTOS = {"ei", "ei,", "ok", "oi", "ola", "hey", "e", "ai", "por", "favor"}

    def __init__(self, wake_word: str = "roberto", variantes: list = None):
        self.wake_word = normalizar(wake_word)
        extras = [normalizar(v) for v in (variantes or [])]
        todas = [self.wake_word] + extras + self.VARIANTES_PADRAO
        # Ordena da maior para a menor para "next us" ganhar de "next".
        self.variantes = sorted(set(v for v in todas if v), key=len, reverse=True)

    def extrair_comando(self, texto: str):
        """
        Devolve o comando SEM a wake word, ou None se a fala não começou com ela.
        String vazia significa "chamou a Roberto e não falou mais nada".

        A wake word precisa vir NO INÍCIO. Só toleramos saudações curtas antes
        ("ei roberto", "ok roberto").

        Por que não aceitar a wake word no meio da frase: o STT transcreve
        qualquer ruído da sala e vira comando por acidente. Num teste real com
        microfone aberto, uma conversa de fundo foi transcrita com o nome da
        assistente no meio — e, com a regra frouxa, isso a acionava e ainda
        gastava uma chamada de LLM.
        """
        normalizado = normalizar(texto)
        # O normalizador preserva pontos para calculos. Aqui eles tambem podem
        # separar nome e comando ("Roberto. Acenda a luz") ou terminar a chamada.
        normalizado = re.sub(r"(?<!\d)[.,](?!\d)|[!?;:]", " ", normalizado)
        normalizado = re.sub(r"\s+", " ", normalizado).strip()
        if not normalizado:
            return None

        # Descarta saudações do começo: "ei ok roberto" -> "roberto"
        tokens = normalizado.split()
        while tokens and tokens[0] in self.PREENCHIMENTOS:
            tokens.pop(0)
        restante = " ".join(tokens)

        for variante in self.variantes:
            if restante == variante:
                return ""  # chamou e não falou mais nada
            # O espaço no final impede casar "robertozinho" ou "nexopolis".
            if restante.startswith(variante + " "):
                return restante[len(variante):].strip(" ,.")
        return None


class Roberto:
    """
    A assistente. Conhece o Listener, o Speaker e o Router — e nada sobre as
    skills individuais. Adicionar comandos não exige tocar nesta classe.
    """

    def __init__(self, listener, speaker, router, llm=None, wake_word: str = "roberto",
                 caminhos: dict = None, variantes: list = None):
        self.listener = listener
        self.speaker = speaker
        self.router = router
        # `variantes` vem do .env (WAKE_WORD_VARIANTES): permite ensinar ao
        # portão como o STT transcreve o nome NA SUA máquina, sem editar código.
        self.gate = WakeWordGate(wake_word, variantes)
        self.estado = Estado.OCIOSO
        self.ctx = Contexto(self, speaker, llm, caminhos or {})
        self._callback_pendente = None
        self._rodando = False

    # ------------------------------------------------------------------
    # Loop principal
    # ------------------------------------------------------------------
    def run(self) -> None:
        """Laço infinito: ouvir -> decidir -> agir. Encerra com Ctrl+C ou "sair"."""
        self._rodando = True
        self.speaker.falar("Roberto online. Diga o meu nome para começar.")
        while self._rodando:
            try:
                self._um_ciclo()
            except KeyboardInterrupt:
                print()
                self.speaker.falar("Encerrando. Até logo!")
                break
            except Exception as erro:
                # Um erro em uma skill não pode derrubar a assistente na demo.
                print(f"[Roberto] Erro inesperado: {erro}")
                self.estado = Estado.OCIOSO
        self.listener.encerrar()

    def _um_ciclo(self) -> None:
        """Uma volta completa do loop: uma escuta e uma reação."""
        aguardando = self.estado is Estado.AGUARDANDO_RESPOSTA
        prompt = "Estou ouvindo a sua resposta..." if aguardando else "Ouvindo..."
        texto = self.listener.ouvir(prompt)

        if not texto:
            return
        print(f"👤 Você disse: {texto}")

        if self._pediu_para_sair(texto):
            self.speaker.falar("Até logo!")
            self._rodando = False
            return

        # --- Estado AGUARDANDO_RESPOSTA -----------------------------------
        # Aqui o gate da wake word fica SUSPENSO de propósito: a fala é a
        # resposta a uma pergunta que a própria Roberto acabou de fazer
        # (item 2). Fora deste estado, a wake word é obrigatória.
        if aguardando and self._callback_pendente:
            self._responder_pendencia(texto)
            return

        # --- Estado OCIOSO: exige wake word (item 1 + Observação) ----------
        comando = self.gate.extrair_comando(texto)
        if comando is None:
            # Sem wake word: apenas imprime o texto reconhecido, sem ação.
            print("   (sem wake word — nenhuma ação executada)")
            return

        if not comando:
            # Chamou só "Roberto": abre um turno de diálogo.
            self.speaker.falar("Pois não?")
            self.ctx.aguardar_resposta(lambda fala, ctx: self.router.route(fala, ctx))
            self._sincronizar_estado()
            return

        self._executar(comando)

    # ------------------------------------------------------------------
    # Execução
    # ------------------------------------------------------------------
    def _executar(self, comando: str) -> None:
        """Manda o comando para o router e fala a resposta."""
        self.estado = Estado.EXECUTANDO
        resposta = self.router.route(comando, self.ctx)
        if resposta:
            self.speaker.falar(resposta)
        self._sincronizar_estado()

    def _responder_pendencia(self, texto: str) -> None:
        """Entrega a fala ao callback registrado pela skill (diálogo aberto)."""
        callback, self._callback_pendente = self._callback_pendente, None
        self.estado = Estado.EXECUTANDO
        resposta = callback(texto, self.ctx)
        if resposta:
            self.speaker.falar(resposta)
        self._sincronizar_estado()

    def _sincronizar_estado(self) -> None:
        """
        Depois de cada execução, a skill pode ter pedido uma resposta.
        Se pediu, guardamos o callback e ficamos em AGUARDANDO_RESPOSTA.
        """
        callback = self.ctx.consumir_callback()
        if callback:
            self._callback_pendente = callback
            self.estado = Estado.AGUARDANDO_RESPOSTA
        else:
            self.estado = Estado.OCIOSO
        print(f"[Estado] {self.estado.value}")

    @staticmethod
    def _pediu_para_sair(texto: str) -> bool:
        return normalizar(texto) in ("sair", "encerrar", "tchau roberto", "desligar")
