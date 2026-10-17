import logging

from aiogram.filters import BaseFilter
from aiogram.types import CallbackQuery, Message

from config import settings

log = logging.getLogger(__name__)


class AllowedUser(BaseFilter):
    """ALLOWED_USER_IDS bo'sh bo'lsa hamma; aks holda faqat ro'yxatdagilar."""

    async def __call__(self, event: Message | CallbackQuery) -> bool:
        allowed = settings.allowed_user_ids
        if not allowed:
            return True
        user = event.from_user
        if user and user.id in allowed:
            return True
        log.warning("Ruxsatsiz foydalanuvchi rad etildi: id=%s", user.id if user else None)
        return False
