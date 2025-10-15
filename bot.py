import discord
from discord.ext import commands, tasks
import os
from dotenv import load_dotenv
import asyncio
import aiohttp
from aiohttp import web
import sys

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração do bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

# Criação do bot e do servidor web
bot = commands.Bot(command_prefix='!', intents=intents)
app = web.Application()

# Configuração do servidor web
async def health_check(request):
    return web.Response(text="Bot is running!")

class SilentSource(discord.PCMVolumeTransformer):
    def __init__(self):
        # Cria um buffer de áudio silencioso
        self._buffer = b'\x00' * 3840  # 20ms de silêncio em 48kHz

    def read(self):
        # Retorna 20ms de silêncio
        return self._buffer

@tasks.loop(seconds=1)
async def play_silence(voice_client):
    """Reproduz silêncio continuamente para manter o bot ativo"""
    if voice_client and voice_client.is_connected():
        if not voice_client.is_playing():
            voice_client.play(SilentSource(), after=lambda e: print(f'Erro ao reproduzir silêncio: {e}' if e else None))

@bot.event
async def on_ready():
    print(f'{bot.user} está online!')
    
    # Conecta ao canal de voz automaticamente
    channel_id = int(os.getenv('VOICE_CHANNEL_ID'))
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            # Se já estiver em um canal de voz, desconecta primeiro
            for vc in bot.voice_clients:
                await vc.disconnect()
            
            # Conecta pelo canal desejado
            voice_client = await channel.connect()
            print(f'Conectado ao canal de voz: {channel.name}')
            
            # Inicia o loop de reprodução de silêncio
            if not play_silence.is_running():
                play_silence.start(voice_client)
        except Exception as e:
            print(f'Erro ao conectar ao canal de voz: {e}')

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

async def start_bot():
    # Configuração das rotas do servidor web
    app.router.add_get("/", health_check)
    
    # Inicia o servidor web
    port = int(os.environ.get("PORT", 10000))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    print(f"Web server started on port {port}")
    
    try:
        # Inicia o bot
        await bot.start(os.getenv('TOKEN'))
    finally:
        if not bot.is_closed():
            await bot.close()
        await runner.cleanup()

# Executa o bot e o servidor web
if __name__ == '__main__':
    try:
        asyncio.run(start_bot())
    except KeyboardInterrupt:
        print("Shutting down...")