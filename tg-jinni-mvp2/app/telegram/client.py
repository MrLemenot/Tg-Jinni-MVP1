from aiogram import Bot


async def get_public_channel(bot: Bot, username: str):
    username = username.strip()
    if username.startswith("https://t.me/"):
        username = "@" + username.rstrip("/").split("/")[-1]
    elif not username.startswith("@"):
        username = "@" + username
    return await bot.get_chat(username)


async def check_admin(bot: Bot, channel_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(channel_id, user_id)
    return member.status in {"administrator", "creator"}


async def check_bot_admin(bot: Bot, channel_id: int) -> bool:
    me = await bot.get_me()
    member = await bot.get_chat_member(channel_id, me.id)
    return member.status in {"administrator", "creator"}


async def check_member(bot: Bot, channel_id: int, user_id: int) -> bool:
    member = await bot.get_chat_member(channel_id, user_id)
    return member.status in {"member", "administrator", "creator"}
