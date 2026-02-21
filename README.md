# @botgate/botgate-stats-reporter-py

[![pypi version](https://img.shields.io/pypi/v/botgate-stats-reporter-py.svg)](https://pypi.org/project/botgate-stats-reporter-py/)
[![license](https://img.shields.io/pypi/l/botgate-stats-reporter-py.svg)](https://github.com/nathan-lucca/botgate-stats-reporter-py/blob/main/LICENSE)

O módulo oficial do **BotGate** para simplificar a integração de bots Discord (Python) com a nossa plataforma. Automatize o envio de estatísticas, monitore votos em tempo real e gerencie o plano do seu bot com facilidade usando `discord.py`.

## 📦 Instalação

```bash
pip install botgate-stats-reporter-py
```

## 🚀 Como usar

A biblioteca foi projetada para ser "configure e esqueça". Ela gerencia automaticamente o intervalo de postagem com base no seu plano (Tier).

### Integração Simples (com Votos em Tempo Real)

```python
import discord
from discord.ext import commands
from botgate_reporter import BotGateReporter

class MyBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=discord.Intents.default())

        # Inicializa o Reporter
        self.reporter = BotGateReporter(
            bot_id="SEU_BOT_ID",
            api_key="SUA_API_KEY",
            enable_webhooks=True, # Ativa o servidor interno para receber votos
            lang="pt-BR",         # Opcional: "pt-BR" (padrão) ou "en-US"
            debug=True            # Opcional: True para logs detalhados
        )

        # Evento disparado sempre que alguém votar no seu bot
        @self.reporter.on("vote")
        async def on_bot_vote(vote):
            print(f"🎁 Recompensa para {vote['username']} por votar!")
            # Sua lógica de cargos ou moedas aqui

    async def setup_hook(self):
        # Inicia o loop automático de estatísticas e heartbeats
        self.reporter.start(self)

bot = MyBot()
bot.run("SEU_TOKEN_DISCORD")
```

### ⚙️ Configuração

O construtor `BotGateReporter` aceita as seguintes opções:

| Propriedade       | Tipo      | Padrão          | Descrição                                                       |
| :---------------- | :-------- | :-------------- | :-------------------------------------------------------------- |
| `bot_id`          | `string`  | **Obrigatório** | O ID do seu bot no Discord.                                     |
| `api_key`         | `string`  | **Obrigatório** | Sua API Key obtida no painel do BotGate.                        |
| `enable_webhooks` | `boolean` | `False`         | Ativa o servidor HTTP interno para receber votos em tempo real. |
| `lang`            | `string`  | `"pt-BR"`       | Idioma dos logs e respostas da API (`pt-BR` ou `en-US`).        |
| `debug`           | `boolean` | `False`         | Ativa logs detalhados no console para depuração.                |

---

## 🛠️ Métodos Principais

| Método                      | Descrição                                                        |
| :-------------------------- | :--------------------------------------------------------------- |
| `start(client)`             | Inicia o loop automático de estatísticas e heartbeats.           |
| `stop()`                    | Interrompe todos os processos em segundo plano.                  |
| `handle_shard_message(msg)` | Processa mensagens IPC para emitir eventos em Shards.            |
| `get_bot_info()`            | Obtém dados completos do perfil do bot e do plano atual.         |
| `get_bot_votes(limit?)`     | Consulta os últimos eleitores e estatísticas de votação.         |
| `get_api_usage()`           | Verifica o consumo mensal da sua cota de API.                    |
| `send_heartbeat()`          | Envia um sinal de vida manual (Exclusivo para o plano Business). |
| `send_stats()`              | Força um envio manual imediato de estatísticas.                  |

---

## ⚡ Monitoramento de Sharding

No Python (`discord.py`), se você estiver usando `AutoShardedBot`, o reporter detecta automaticamente o Shard Líder (ID 0) para realizar o reporte global, evitando duplicação de dados.

Para repassar votos entre processos (se usar sharding multi-processual), use o método:

```python
# Ao receber uma mensagem IPC/Rede com o voto
reporter.handle_shard_message(message_data)
```

## 🧠 Sincronização Inteligente

O `botgate-stats-reporter-py` é reativo. Se você fizer um upgrade de plano no painel do BotGate, o bot detectará os novos limites na próxima comunicação com o servidor e ajustará o intervalo de postagem automaticamente.

- **Auto-Configuração**: Tenta detectar seu IP (Local, Público ou Cloud Run) e configurar o Webhook no painel automaticamente.
- **Dual-Webhook**: Alertas de erro continuam indo para o seu Discord, enquanto os dados de voto vão direto para o código do bot.
- **Hot-Swap**: Acelera o intervalo de envio conforme o novo Tier sem precisar reiniciar o bot.

## 🔗 Links Úteis

- [Documentação Oficial](https://docs-botgate.vercel.app/)
- [Painel do Desenvolvedor](https://botgate-site.vercel.app/settings)
- [Suporte no Discord](https://www.discord.gg/xK4r9HqKKf)

## 📄 Licença

Distribuído sob a licença MIT. Veja `LICENSE` para mais informações.
