# CP6 - makerlab robô inteligente

Roberto é um robô controlado por voz ou texto. O computador interpreta o pedido e fala a resposta; o Arduino Uno controla um servo SG90 e um LED por USB.

Este repositório contém somente código e instruções de software/eletrônica. Não inclui modelagem 3D, arquivos de corte, modelos de IA, executáveis, gravações ou dados pessoais. A versão ativa não usa webcam, reconhecimento facial ou simulação.

## Recursos

- Interface local simples para conversar por texto e voz.
- Reconhecimento em português com **Whisper small**, via faster-whisper, CPU INT8.
- Conversa com **Gemma 3 1B**, pela API local do Ollama.
- Voz masculina brasileira **Piper Cadu**.
- Controle real do braço e do LED, com confirmação correlacionada por USB.
- Conexão automática ao Arduino quando há uma única placa USB disponível.
- Botões físicos independentes da fila da IA: uma pergunta lenta não bloqueia o envio de ações ao Arduino.

O áudio não é enviado para uma API externa no funcionamento padrão. Não é necessária chave de API. É preciso internet para instalar dependências e baixar os modelos; depois, as funções principais podem operar localmente.

## Organização

| Caminho | Função |
|---|---|
| `app.py` | Servidor FastAPI em `127.0.0.1:8765` |
| `web/index.html` | Interface leve, sem câmera ou animação de simulação |
| `core/simple_runtime.py` | Coordenação de conversa, voz e comandos reais |
| `core/local_audio.py` | Captura, transcrição e síntese de voz |
| `core/llm.py` | Cliente de IA; a configuração padrão usa Ollama local |
| `core/robot.py` | Identificação de comandos e protocolo serial com ACK |
| `core/assistant.py` | Portão da palavra de ativação; também preserva uma classe auxiliar legada |
| `firmware/Roberto/Roberto.ino` | Programa do Arduino |
| `tools/` | Preparação de modelos e compilação do firmware |
| `tests/` | Testes automatizados sem exigir Arduino conectado |

## Preparar em outro computador Windows

Recomendado: **Python 3.12 de 64 bits**, com suporte a Tkinter. Execute na pasta do projeto:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe tools/preparar_local.py all
```

A preparação baixa o Ollama portátil, o Whisper small e a voz Cadu para as pastas locais ignoradas pelo Git. O download pode ocupar vários GB.

Para baixar o modelo de conversa, abra um PowerShell na pasta do projeto e inicie o Ollama:

```powershell
$env:OLLAMA_HOST='127.0.0.1:11435'
$env:OLLAMA_MODELS=Join-Path (Get-Location) 'models\ollama'
$env:OLLAMA_NO_CLOUD='1'
.\runtime\ollama\ollama.exe serve
```

Em outro PowerShell, também na pasta do projeto:

```powershell
$env:OLLAMA_HOST='127.0.0.1:11435'
.\runtime\ollama\ollama.exe pull gemma3:1b
```

Depois, dê dois cliques em **INICIAR_ROBERTO.bat**. O inicializador reutiliza o Ollama se ele já estiver rodando e abre [o painel local](http://127.0.0.1:8765/).

## Microfone e saída de áudio

`config_roberto.json` usa os dispositivos padrão do Windows. Para selecionar outro, altere `dispositivo_microfone` ou `dispositivo_saida` e reinicie o aplicativo. `null` usa o padrão; um nome de dispositivo também pode ser informado.

Diga **“Roberto, acenda a luz”**, **“Roberto, levante o braço”** ou faça uma pergunta. No campo de texto, o nome Roberto é opcional. Aguarde a fala terminar antes de falar novamente: a captura é bloqueada durante a reprodução para evitar que ele responda à própria voz.

O Whisper ainda pode levar alguns segundos para reconhecer uma frase em computadores mais antigos. Os botões enviam ações diretamente ao Arduino, sem passar pela IA.

## Arduino e ligações

Firmware destinado a **Uno R3 / Nano clássico ATmega328P de 5 V**. Não presumir compatibilidade elétrica com outras placas.

| Componente | Ligação |
|---|---|
| SG90: sinal laranja/amarelo | **D9** |
| SG90: vermelho | **5V** ou alimentação externa apropriada |
| SG90: marrom/preto | **GND** |
| LED: anodo | **D6 em série com resistor externo**, por exemplo 330 Ω |
| LED: catodo | **GND** |

**Este firmware exige resistor externo no LED.** Ele usa saída `OUTPUT/HIGH` para acender; não use a montagem antiga sem resistor. Faça alterações nas ligações com a alimentação desligada.

O braço usa **90° para abaixar e 180° para levantar**, conforme a montagem ensaiada. Teste inicialmente sem carga, deixe espaço para o movimento e ajuste os limites se houver colisão ou esforço no fim do curso. Não force o eixo com a mão.

Se a alimentação USB não sustentar o servo, use uma fonte apropriada para ele, com GND compartilhado com o Arduino. Não una inadvertidamente os positivos da fonte externa e do USB.

### Compilar e gravar

Com as dependências instaladas:

```powershell
.\.venv\Scripts\python.exe tools/preparar_arduino.py
```

Isso baixa as ferramentas oficiais da Arduino e compila o firmware para Uno e variantes Nano. Os arquivos compilados não são versionados. Para gravar, feche o Roberto (liberando a porta COM), mantenha inicialmente LED e servo desconectados e execute **GRAVAR_ARDUINO.bat**. Selecione placa e porta corretas; a gravação substitui o programa atual da placa.

Também é possível abrir `firmware/Roberto/Roberto.ino` na Arduino IDE, instalar a biblioteca **Servo**, selecionar a placa/porta e carregar o programa.

Ao iniciar o Roberto, a placa USB é conectada automaticamente quando identificável. Se necessário, use **Conexão USB** no painel para escolher outra porta. Se a placa for desconectada, reconecte a porta antes de repetir o comando.

### Protocolo

O computador envia uma linha JSON:

```json
{"id":"abc123","action":"ARM_UP"}
```

A placa responde com o mesmo identificador após executar:

```json
{"id":"abc123","ok":true}
```

Ações: `ARM_UP`, `ARM_DOWN`, `LED_ON`, `LED_OFF` e `WAVE`. A confirmação valida a execução do firmware; não mede a posição física, pois o projeto não tem sensor no braço. Sem confirmação, o aplicativo não informa sucesso.

## Testes

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

Os testes verificam roteamento, negação de comandos, ausência de falso sucesso, respostas faladas e independência dos controles físicos em relação à conversa. Não substituem ensaios elétricos e mecânicos.

## Créditos

Projeto adaptado a partir de [jzampieri/cp_04_iot](https://github.com/jzampieri/cp_04_iot). A versão CP6 reúne a interface simples, processamento local e integração com o robô. Dependências e modelos de terceiros têm suas próprias licenças, que devem ser observadas separadamente.
