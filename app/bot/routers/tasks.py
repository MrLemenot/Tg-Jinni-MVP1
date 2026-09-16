from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, WebAppInfo
from app.config.settings import get_settings
router = Router()

@router.message(Command('tasks'))
async def tasks(message: Message):
    s = get_settings()
    await message.answer('🎁 Задания доступны в Mini App.', reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text='Открыть задания', web_app=WebAppInfo(url=s.public_webapp_url + '?screen=tasks'))
    ]]))
