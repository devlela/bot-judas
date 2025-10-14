import discord
from discord.ext import commands
import os
from dotenv import load_dotenv

# Carrega as variáveis de ambiente do arquivo .env
load_dotenv()

# Configuração do bot
intents = discord.Intents.default()
intents.message_content = True
intents.voice_states = True

bot = commands.Bot(command_prefix='!', intents=intents)

@bot.event
async def on_ready():
    print(f'{bot.user} está online!')
    # Conecta ao canal de voz automaticamente
    channel_id = int(os.getenv('VOICE_CHANNEL_ID'))
    channel = bot.get_channel(channel_id)
    if channel:
        try:
            await channel.connect()
            print(f'Conectado ao canal de voz: {channel.name}')
        except Exception as e:
            print(f'Erro ao conectar ao canal de voz: {e}')

@bot.command()
async def join(ctx):
    """Comando para fazer o bot entrar no canal de voz"""
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        try:
            await channel.connect()
            await ctx.send(f'Conectado ao canal: {channel.name}')
        except Exception as e:
            await ctx.send(f'Erro ao conectar: {e}')
    else:
        await ctx.send('Você precisa estar em um canal de voz!')

@bot.command()
async def leave(ctx):
    """Comando para fazer o bot sair do canal de voz"""
    if ctx.voice_client:
        await ctx.voice_client.disconnect()
        await ctx.send('Desconectado do canal de voz!')
    else:
        await ctx.send('Não estou em nenhum canal de voz!')

# Inicia o bot com o token
bot.run(os.getenv('TOKEN'))