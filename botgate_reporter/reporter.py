import asyncio
import logging
import aiohttp
from aiohttp import web
from typing import Optional, Dict, Any, List, Callable
from discord.ext import tasks
import time
from . import __version__
import os

logger = logging.getLogger("botgate_reporter")

DEFAULT_API_URL = "https://api.botgate.coden8n.shop"

STRINGS = {
    "pt-BR": {
        "initialized": "✅ BotGate Reporter inicializado",
        "webhook_listening": "📡 Servidor de webhook ouvindo na porta {port}",
        "starting_auto_config": "🔍 Iniciando auto-configuração...",
        "detected_gcr": "☁️ Ambiente Google Cloud Run detectado (Projeto: {project})",
        "failed_gcr_metadata": "⚠️ Cloud Run detectado, mas falha ao obter ID do projeto",
        "detected_localhost": "🏠 Ambiente localhost detectado",
        "detected_public_ip": "🌐 IP público detectado: {ip}",
        "auto_config_success": "✅ Webhook auto-configurado com sucesso no BotGate",
        "auto_config_failed": "❌ Auto-configuração falhou",
        "reporter_started": "🚀 Reporter iniciado",
        "reporter_stopped": "🛑 Reporter parado",
        "api_key_verify_failed": "❌ Falha na verificação da API key",
        "bot_ready": "🤖 Bot pronto: {tag}",
        "shard_leader_detected": "⭐ Shard Leader detectado. Lidando com reporte global.",
        "shard_initialized_skip": "ℹ️ Shard #{id} inicializado. Pulando reporte (Tarefa do Líder).",
        "auto_stats_enabled": "⏰ Auto-stats ativado (cada {min} min)",
        "heartbeat_enabled": "💓 Business Heartbeat ativado (cada 5 min)",
        "plan_change_detected": "🔄 Mudança de plano detectada: {old} -> {new}",
        "limit_reached": "⚠️ Limite de Tier/Frequência atingido ({status}). Sincronizando e aguardando próximo ciclo...",
    },
    "en-US": {
        "initialized": "✅ BotGate Reporter initialized",
        "webhook_listening": "📡 Webhook server listening on port {port}",
        "starting_auto_config": "🔍 Starting auto-configuration...",
        "detected_gcr": "☁️ Detected Google Cloud Run environment (Project: {project})",
        "failed_gcr_metadata": "⚠️ Cloud Run detected but failed to get project ID",
        "detected_localhost": "🏠 Detected localhost environment",
        "detected_public_ip": "🌐 Detected public IP: {ip}",
        "auto_config_success": "✅ Webhook auto-configured successfully on BotGate",
        "auto_config_failed": "❌ Auto-configuration failed",
        "reporter_started": "🚀 Reporter started",
        "reporter_stopped": "🛑 Reporter stopped",
        "api_key_verify_failed": "❌ API key verification failed",
        "bot_ready": "🤖 Bot ready: {tag}",
        "shard_leader_detected": "⭐ Shard Leader detected. Handling global reporting.",
        "shard_initialized_skip": "ℹ️ Shard #{id} initialized. Skipping reporting (Leader task).",
        "auto_stats_enabled": "⏰ Auto-stats enabled ({min} min)",
        "heartbeat_enabled": "💓 Business Heartbeat enabled (every 5 min)",
        "plan_change_detected": "🔄 Plan change detected: {old} -> {new}",
        "limit_reached": "⚠️ Tier/Frequency limit reached ({status}). Syncing and waiting for next cycle...",
    },
}


class BotGateReporter:
    def __init__(
        self,
        bot_id: str,
        api_key: str,
        enable_webhooks: bool = False,
        webhook_port: int = 8080,
        auto_config: bool = True,
        debug: bool = False,
        lang: str = "pt-BR",
        api_url: Optional[str] = None,
    ):
        self.bot_id = bot_id
        self.api_key = api_key
        self.enable_webhooks = enable_webhooks
        self.webhook_port = webhook_port
        self.auto_config = auto_config
        self.debug = debug
        self.lang = lang if lang in STRINGS else "pt-BR"
        self.api_url = api_url or os.environ.get("BOTGATE_API_URL") or DEFAULT_API_URL

        self.client = None
        self.current_tier = ""
        self.update_interval = 30  # Minutos
        self.is_running = False
        self.events: Dict[str, List[Callable]] = {"vote": []}

        # Setup Logger
        if self.debug:
            logger.setLevel(logging.DEBUG)
            if not logger.handlers:
                h = logging.StreamHandler()
                h.setFormatter(
                    logging.Formatter(
                        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
                    )
                )
                logger.addHandler(h)

        self.session: Optional[aiohttp.ClientSession] = None
        self._t = STRINGS[self.lang]
        logger.info(self._t["initialized"])

    def on(self, event_name: str):
        """Decorator para registrar eventos (atualmente suporta: 'vote')"""

        def decorator(func: Callable):
            if event_name in self.events:
                self.events[event_name].append(func)
            return func

        return decorator

    async def _emit(self, event_name: str, data: Any):
        if event_name in self.events:
            for callback in self.events[event_name]:
                if asyncio.iscoroutinefunction(callback):
                    await callback(data)
                else:
                    callback(data)

    def _get_headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"BotGate-Stats-Reporter-Py/{__version__} (Bot: {self.bot_id})",
        }

    async def _ensure_session(self):
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(headers=self._get_headers())

    async def init_webhook_server(self):
        """Inicializa o servidor de webhooks interno para receber votos"""
        app = web.Application()
        app.router.add_post("/webhook", self._handle_webhook)
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "0.0.0.0", self.webhook_port)
        await site.start()
        logger.info(self._t["webhook_listening"].format(port=self.webhook_port))

    async def _handle_webhook(self, request):
        try:
            body = await request.json()
            # Emite o evento 'vote' com os detalhes
            await self._emit("vote", body.get("details", body))
            return web.json_response({"success": True})
        except Exception:
            return web.Response(status=400)

    async def setup_auto_webhook(self):
        """Auto-configuração do Webhook no BotGate"""
        logger.info(self._t["starting_auto_config"])
        try:
            webhook_url = ""
            import os

            if os.environ.get("K_SERVICE"):  # Google Cloud Run
                async with aiohttp.ClientSession() as s:
                    async with s.get(
                        "http://metadata.google.internal/computeMetadata/v1/project/numeric-project-id",
                        headers={"Metadata-Flavor": "Google"},
                    ) as r:
                        project = await r.text()
                        region = os.environ.get("GOOGLE_CLOUD_REGION", "us-central1")
                        webhook_url = f"https://{os.environ.get('K_SERVICE')}-{project}.{region}.run.app/webhook"
                        logger.info(self._t["detected_gcr"].format(project=project))
            elif "localhost" in self.api_url or "127.0.0.1" in self.api_url:
                webhook_url = f"http://localhost:{self.webhook_port}/webhook"
                logger.info(self._t["detected_localhost"])
            else:
                async with aiohttp.ClientSession() as s:
                    async with s.get("https://api.ipify.org?format=json") as r:
                        ip_data = await r.json()
                        public_ip = ip_data["ip"]
                        webhook_url = f"http://{public_ip}:{self.webhook_port}/webhook"
                        logger.info(self._t["detected_public_ip"].format(ip=public_ip))

            if webhook_url:
                secret = os.urandom(8).hex()
                await self._ensure_session()
                async with self.session.post(
                    f"{self.api_url}/api/v1/settings/webhook",
                    json={"url": webhook_url, "secret": secret, "isReporter": True},
                ) as r:
                    res = await r.json()
                    if res.get("success"):
                        logger.info(self._t["auto_config_success"])
        except Exception as e:
            logger.error(self._t["auto_config_failed"] + f": {str(e)}")

    async def verify_api_key(self) -> bool:
        await self._ensure_session()
        try:
            async with self.session.get(
                f"{self.api_url}/api/v1/verify", params={"lang": self.lang}
            ) as r:
                res = await r.json()
                if res.get("success"):
                    self._sync_from_response(res.get("data", {}))
                    return True
                logger.error(self._t["api_key_verify_failed"])
                return False
        except Exception as e:
            logger.error(f"Error verifying API key: {str(e)}")
            return False

    def _sync_from_response(self, data: Dict):
        if not data:
            return
        tier_obj = data.get("tier", data)
        tier_name = tier_obj.get("name") or tier_obj.get("tier") or data.get("tier")

        if tier_name and tier_name != self.current_tier:
            logger.info(
                self._t["plan_change_detected"].format(
                    old=self.current_tier, new=tier_name
                )
            )
            self.current_tier = tier_name

        interval = tier_obj.get("updateIntervalMinutes") or data.get(
            "updateIntervalMinutes"
        )
        if interval and interval != self.update_interval:
            self.update_interval = interval
            if self.is_running:
                self._stats_loop.change_interval(minutes=self.update_interval)

    def handle_shard_message(self, message: Any):
        """Método útil para lidar com mensagens de Shards (IPC)"""
        if (
            message
            and isinstance(message, dict)
            and message.get("type") == "BOTGATE_VOTE"
        ):
            asyncio.create_task(self._emit("vote", message.get("data")))

    async def _on_ready(self):
        logger.info(self._t["bot_ready"].format(tag=str(self.client.user)))

        # Apenas o Shard Leader (ID 0) ou bot sem shards faz o reporte
        shard_id = self.client.shard_id if hasattr(self.client, "shard_id") else 0
        if shard_id is None:
            shard_id = 0

        is_leader = shard_id == 0

        if is_leader:
            logger.info(self._t["shard_leader_detected"])
            await self.verify_api_key()
            await self.send_stats()

            if not self._stats_loop.is_running():
                self._stats_loop.start()
                logger.info(
                    self._t["auto_stats_enabled"].format(min=self.update_interval)
                )

            self._manage_heartbeat()
        else:
            logger.info(self._t["shard_initialized_skip"].format(id=shard_id))

    def _manage_heartbeat(self):
        if self.current_tier == "business":
            if not self._heartbeat_loop.is_running():
                self._heartbeat_loop.start()
                logger.info(self._t["heartbeat_enabled"])
        elif self._heartbeat_loop.is_running():
            self._heartbeat_loop.stop()

    async def send_stats(self):
        if not self.client or not self.client.is_ready():
            return

        await self._ensure_session()

        # No discord.py, len(client.guilds) já é o total do processo
        server_count = len(self.client.guilds)
        user_count = sum(guild.member_count or 0 for guild in self.client.guilds)
        shard_count = getattr(self.client, "shard_count", 1) or 1

        payload = {
            "botId": self.bot_id,
            "serverCount": server_count,
            "userCount": user_count,
            "shardCount": shard_count,
            "lang": self.lang,
            "timestamp": int(time.time() * 1000),
        }

        try:
            async with self.session.post(
                f"{self.api_url}/api/v1/bots/stats", json=payload
            ) as r:
                res = await r.json()
                if res.get("success"):
                    self._sync_from_response(res.get("data", {}))
                    logger.debug(f"Stats sent: {server_count} guilds")
                elif r.status in [403, 429]:
                    logger.warning(self._t["limit_reached"].format(status=r.status))
                    await self.verify_api_key()
        except Exception as e:
            logger.error(f"Error sending stats: {str(e)}")

    async def send_heartbeat(self):
        if self.current_tier != "business":
            return
        await self._ensure_session()
        try:
            await self.session.post(
                f"{self.api_url}/api/v1/heartbeat", json={"lang": self.lang}
            )
        except Exception:
            pass

    @tasks.loop(minutes=30)
    async def _stats_loop(self):
        await self.send_stats()

    @tasks.loop(minutes=5)
    async def _heartbeat_loop(self):
        await self.send_heartbeat()

    @_stats_loop.before_loop
    async def _before_stats(self):
        await self.client.wait_until_ready()

    def start(self, client):
        self.client = client
        self.is_running = True

        # Registra o evento ready do discord.py
        if client.is_ready():
            asyncio.create_task(self._on_ready())
        else:
            # Gambiarra técnica para adicionar um listener sem sobrescrever o do usuário
            client.event(self._on_ready)

        if self.enable_webhooks:
            asyncio.create_task(self.init_webhook_server())

        if self.auto_config:
            asyncio.create_task(self.setup_auto_webhook())

        logger.info(self._t["reporter_started"])

    def stop(self):
        self._stats_loop.stop()
        self._heartbeat_loop.stop()
        self.is_running = False
        if self.session:
            asyncio.create_task(self.session.close())
        logger.info(self._t["reporter_stopped"])

    # API Wrappers
    async def get_bot_info(self) -> Dict:
        await self._ensure_session()
        async with self.session.get(f"{self.api_url}/api/v1/bots/{self.bot_id}") as r:
            return await r.json()

    async def get_bot_votes(self, limit: int = 10) -> Dict:
        await self._ensure_session()
        async with self.session.get(
            f"{self.api_url}/api/v1/bots/{self.bot_id}/votes", params={"limit": limit}
        ) as r:
            return await r.json()

    async def get_api_usage(self) -> Dict:
        await self._ensure_session()
        async with self.session.get(f"{self.api_url}/api/v1/usage") as r:
            res = await r.json()
            if res.get("success"):
                self._sync_from_response(res.get("data", {}))
            return res

    async def get_bot_analytics(self) -> Dict:
        """Busca métricas e analytics (Requer plano compatível)"""
        await self._ensure_session()
        async with self.session.get(
            f"{self.api_url}/api/v1/bots/{self.bot_id}/analytics"
        ) as r:
            return await r.json()

    async def get_stats_history(self, period: str = "all") -> Dict:
        """Busca histórico de crescimento (Para gráficos)"""
        await self._ensure_session()
        async with self.session.get(
            f"{self.api_url}/api/v1/bots/{self.bot_id}/stats/history",
            params={"period": period},
        ) as r:
            return await r.json()
