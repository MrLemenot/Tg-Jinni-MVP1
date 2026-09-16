from aiogram import Router
from aiogram.filters import CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from app.config.settings import get_settings

router = Router()

@router.message(CommandStart())
async def start(message: Message):
    s = get_settings()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text='🎮 Начать игру', web_app=WebAppInfo(url=s.public_webapp_url))],
        [InlineKeyboardButton(text='🎁 Задания', web_app=WebAppInfo(url=s.public_webapp_url + '?screen=tasks'))],
        [InlineKeyboardButton(text='📺 Мои каналы', web_app=WebAppInfo(url=s.public_webapp_url + '?screen=channels'))],
    ])
    await message.answer('🧞‍♂️ ТГ-Джинни\n\nЯ попробую угадать, кого или что ты загадал.', reply_markup=kb)
