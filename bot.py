import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import asyncio
from aiohttp import web, ClientSession
import logging
import time

# Configurar logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração do bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True
intents.guilds = True

# Criação do bot
bot = commands.Bot(command_prefix='!', intents=intents)

# Variáveis globais para monitoramento
last_voice_time = time.time()
is_reconnecting = False

# Criar a aplicação web
app = web.Application()
runner = None  # Será definido mais tarde

class SilentSource(discord.PCMVolumeTransformer):
    def __init__(self):
        self._buffer = b'\x00' * 3840  # 20ms de silêncio em 48kHz
        super().__init__(discord.AudioSource())
        self.volume = 0.01  # Volume muito baixo para ser praticamente inaudível

    def read(self):
        global last_voice_time
        last_voice_time = time.time()
        return self._buffer

    def cleanup(self):
        pass

@tasks.loop(seconds=20)
async def play_silence(voice_client):
    """Reproduz silêncio continuamente para manter o bot ativo"""
    if voice_client and voice_client.is_connected():
        if not voice_client.is_playing():
            try:
                voice_client.play(SilentSource(), after=lambda e: logger.error(f'Erro ao reproduzir silêncio: {e}') if e else None)
                logger.info("Iniciando reprodução de silêncio")
                global last_voice_time
                last_voice_time = time.time()
            except Exception as e:
                logger.error(f"Erro ao iniciar reprodução de silêncio: {e}")

@tasks.loop(seconds=30)
async def check_voice_connection():
    """Verifica e mantém a conexão de voz"""
    global is_reconnecting
    if is_reconnecting:
        return

    try:
        channel_id = int(os.getenv('VOICE_CHANNEL_ID'))
        is_in_correct_channel = any(vc.channel.id == channel_id for vc in bot.voice_clients if vc.is_connected())
        
        if not is_in_correct_channel:
            is_reconnecting = True
            logger.info("Detectada desconexão do canal de voz. Tentando reconectar...")
            
            # Desconecta de qualquer canal atual
            for vc in bot.voice_clients:
                try:
                    if play_silence.is_running():
                        play_silence.stop()
                    await vc.disconnect()
                except:
                    pass
            
            # Conecta ao canal correto
            channel = bot.get_channel(channel_id)
            if channel:
                try:
                    voice_client = await channel.connect()
                    await asyncio.sleep(1)  # Pequena pausa para estabilizar a conexão
                    if not play_silence.is_running():
                        play_silence.start(voice_client)
                    logger.info(f"Reconectado ao canal de voz: {channel.name}")
                except Exception as e:
                    logger.error(f"Erro ao reconectar: {e}")
            else:
                logger.error("Canal de voz não encontrado")
    except Exception as e:
        logger.error(f"Erro ao verificar conexão de voz: {e}")
    finally:
        is_reconnecting = False

@tasks.loop(seconds=60)
async def keep_alive():
    """Mantém o serviço ativo fazendo auto-ping"""
    try:
        async with ClientSession() as session:
            async with session.get(f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME', 'bot-judas.onrender.com')}") as response:
                logger.info(f"Auto-ping status: {response.status}")
    except Exception as e:
        logger.error(f"Erro no auto-ping: {e}")

@tasks.loop(minutes=2)
async def connection_watchdog():
    """Monitor de conexão que verifica se o áudio está sendo reproduzido"""
    global last_voice_time, is_reconnecting
    
    if time.time() - last_voice_time > 60:  # 1 minuto sem atividade de áudio
        if not is_reconnecting:
            logger.warning("Detectada inatividade de áudio. Reiniciando reprodução...")
            for vc in bot.voice_clients:
                if vc.is_connected() and not vc.is_playing():
                    try:
                        vc.play(SilentSource(), after=lambda e: logger.error(f'Erro ao reproduzir silêncio: {e}') if e else None)
                        logger.info("Reprodução de áudio reiniciada")
                    except Exception as e:
                        logger.error(f"Erro ao reiniciar áudio: {e}")
                        await check_voice_connection()
    
    # Verifica se o bot ainda está no canal correto
    channel_id = int(os.getenv('VOICE_CHANNEL_ID'))
    if not any(vc.channel.id == channel_id for vc in bot.voice_clients if vc.is_connected()):
        logger.warning("Bot não está no canal correto. Reconectando...")
        await check_voice_connection()

@bot.event
async def on_ready():
    logger.info(f'{bot.user} está online!')
    
    # Inicia os loops de monitoramento
    if not check_voice_connection.is_running():
        check_voice_connection.start()
    if not keep_alive.is_running():
        keep_alive.start()
    if not connection_watchdog.is_running():
        connection_watchdog.start()
    
    # Conecta ao canal de voz automaticamente
    channel_id = int(os.getenv('VOICE_CHANNEL_ID'))
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            # Se já estiver em um canal de voz, desconecta primeiro
            for vc in bot.voice_clients:
                await vc.disconnect()
            
            # Conecta ao canal desejado
            voice_client = await channel.connect()
            logger.info(f'Conectado ao canal de voz: {channel.name}')
            
            # Inicia o loop de reprodução de silêncio
            if not play_silence.is_running():
                play_silence.start(voice_client)
        except Exception as e:
            logger.error(f'Erro ao conectar ao canal de voz: {e}')

@bot.command()
async def join(ctx):
    """Comando para fazer o bot entrar no canal de voz"""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        try:
            voice_client = await channel.connect()
            await ctx.send(f'Conectado ao canal: {channel.name}')
            # Inicia o loop de reprodução de silêncio
            if not play_silence.is_running():
                play_silence.start(voice_client)
        except Exception as e:
            await ctx.send(f'Erro ao conectar: {e}')
    else:
        await ctx.send('Você precisa estar em um canal de voz!')

@bot.command()
async def leave(ctx):
    """Comando para fazer o bot sair do canal de voz"""
    if ctx.voice_client:
        # Para o loop de reprodução de silêncio
        if play_silence.is_running():
            play_silence.stop()
        await ctx.voice_client.disconnect()
        await ctx.send('Desconectado do canal de voz!')
    else:
        await ctx.send('Não estou em nenhum canal de voz!')

# Rotas do servidor web
async def health_check(request):
    # Verificar se o bot está conectado ao Discord e ao canal de voz
    is_discord_connected = bot.is_ready()
    is_voice_connected = any(vc.is_connected() for vc in bot.voice_clients)
    
    status = {
        "status": "healthy" if is_discord_connected and is_voice_connected else "degraded",
        "discord_connected": is_discord_connected,
        "voice_connected": is_voice_connected,
        "last_voice_activity": time.time() - last_voice_time,
        "uptime": time.time() - bot.start_time if hasattr(bot, 'start_time') else 0
    }
    
    # Se estiver degradado, tentar reconectar
    if not is_voice_connected and not is_reconnecting:
        asyncio.create_task(check_voice_connection())
    
    return web.json_response(status)

app.router.add_get("/", health_check)
app.router.add_get("/health", health_check)  # Endpoint adicional para monitoramento

async def start():
    global runner
    
    # Iniciar o servidor web
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    
    try:
        await site.start()
        logger.info(f"Servidor web iniciado na porta {port}")
        
        # Registrar tempo de início
        bot.start_time = time.time()
        
        # Conectar o bot
        await bot.start(os.getenv('TOKEN'))
    except Exception as e:
        logger.error(f"Erro ao iniciar: {e}")
        if runner:
            await runner.cleanup()
        raise

# Executar o bot e o servidor web
if __name__ == "__main__":
    try:
        asyncio.run(start())
    except KeyboardInterrupt:
        logger.info("Desligando o bot...")
    except Exception as e:
        logger.error(f"Erro fatal: {e}")
        raise
