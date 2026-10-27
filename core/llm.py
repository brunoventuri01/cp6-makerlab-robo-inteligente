"""
Cliente único de IA generativa (item 9 da rubrica).

Centralizamos o SDK da OpenAI aqui porque ele é usado por três consumidores
diferentes: a GenerativeSkill (conversa livre), o CommandRouter (function
calling como fallback de roteamento) e o WhisperSTT (transcrição).

O modelo NÃO é hardcoded: vem de OPENAI_MODEL no .env. Modelos são
depreciados com frequência — confira no dashboard da sua conta quais estão
ativos antes da apresentação.
"""

import os


class LLMClient:
    """Fachada fina sobre o SDK da OpenAI, com degradação graciosa."""

    def __init__(self, api_key: str = None, modelo: str = None):
        self.backend = os.getenv("LLM_BACKEND", "ollama")
        self.url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11435").rstrip("/")
        if self.backend == "ollama":
            self.modelo = modelo or os.getenv("OLLAMA_MODEL", "gemma3:4b")
            self.cliente = None
            return
        self.modelo = modelo or os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
        self.cliente = self._conectar(api_key or os.getenv("OPENAI_API_KEY"))

    @property
    def disponivel(self) -> bool:
        """False quando não há chave/SDK: o programa roda mesmo assim, só sem LLM."""
        return self.backend == "ollama" or self.cliente is not None

    @staticmethod
    def _conectar(api_key):
        if not api_key:
            print("[LLM] OPENAI_API_KEY ausente — recursos de IA generativa desligados.")
            return None
        try:
            from openai import OpenAI
        except ImportError:
            print("[LLM] SDK 'openai' não instalado — recursos de IA desligados.")
            return None
        try:
            return OpenAI(api_key=api_key)
        except Exception as erro:
            print(f"[LLM] Falha ao criar cliente: {erro}")
            return None

    def conversar(self, mensagens: list, temperatura: float = 0.7,
                  max_tokens: int = 300) -> str:
        """Chat simples: recebe a lista de mensagens e devolve o texto da resposta."""
        if not self.disponivel:
            return ""
        if self.backend == "ollama":
            import requests
            resposta = requests.post(self.url + "/api/chat", json={
                "model": self.modelo, "messages": mensagens, "stream": False,
                "options": {"temperature": temperatura, "num_predict": max_tokens, "num_ctx": getattr(self,'num_ctx',4096)},
                "keep_alive": "20m",
            }, timeout=(5, getattr(self,'read_timeout',120)))
            resposta.raise_for_status()
            return resposta.json()["message"]["content"].strip()
        try:
            resposta = self.cliente.chat.completions.create(
                model=self.modelo,
                messages=mensagens,
                temperature=temperatura,
                max_tokens=max_tokens,
            )
            return (resposta.choices[0].message.content or "").strip()
        except Exception as erro:
            print(f"[LLM] Erro na chamada: {erro}")
            return ""

    def escolher_ferramenta(self, texto: str, ferramentas: list, system: str = ""):
        """
        Function calling: entrega ao modelo o catálogo de skills e pergunta
        qual delas atende a frase. Devolve (nome_da_ferramenta, argumentos)
        ou (None, None) se o modelo achar que nenhuma serve.

        É isso que faz "Roberto, anota aí que tenho prova de cálculo quinta"
        funcionar sem que ninguém tenha previsto essa frase na regex.
        """
        if not self.disponivel or not ferramentas:
            return None, None

        if self.backend == "ollama":
            # Gemma nao exige suporte nativo a tool calling; JSON validado contra catalogo.
            import requests, json
            prompt = ("Selecione UMA ferramenta do catálogo para o pedido. "
                      "Se nenhuma for apropriada, use nome null. "
                      "Responda JSON {\"nome\":null,\"argumentos\":{}}. "
                      "Nao use ferramenta apenas por palavras relacionadas: respeite o pedido. Catálogo: "
                      + json.dumps(ferramentas, ensure_ascii=False))
            resposta=requests.post(self.url+"/api/chat",json={
                "model":self.modelo,"stream":False,"format":"json",
                "messages":[{"role":"system","content":prompt},{"role":"user","content":texto}],
                "options":{"temperature":0,"num_predict":160,"num_ctx":getattr(self,'num_ctx',4096)}},timeout=(5,90))
            resposta.raise_for_status()
            value=json.loads(resposta.json()["message"]["content"])
            name=value.get('nome'); args=value.get('argumentos',{})
            return (name,args) if name in {f['name'] for f in ferramentas} and isinstance(args,dict) else (None,None)

        payload = [{"type": "function", "function": f} for f in ferramentas]
        mensagens = [
            {"role": "system", "content": system or
             "Você roteia comandos de voz em português para ferramentas. "
             "Se nenhuma ferramenta atender ao pedido, responda em texto sem chamar nada."},
            {"role": "user", "content": texto},
        ]
        try:
            resposta = self.cliente.chat.completions.create(
                model=self.modelo,
                messages=mensagens,
                tools=payload,
                tool_choice="auto",
                temperature=0,
            )
            chamadas = resposta.choices[0].message.tool_calls
            if not chamadas:
                return None, None
            import json

            chamada = chamadas[0]
            argumentos = json.loads(chamada.function.arguments or "{}")
            return chamada.function.name, argumentos
        except Exception as erro:
            print(f"[LLM] Erro no function calling: {erro}")
            return None, None
