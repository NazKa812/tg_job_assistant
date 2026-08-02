import os
import re
from telethon import TelegramClient, events
from config import TELEGRAM_API_ID, TELEGRAM_API_HASH, SESSION_PATH
from telethon.network import ConnectionTcpMTProxyRandomizedIntermediate


class TelegramWorker:
    def __init__(self, api_id: str = None, api_hash: str = None):
        self.api_id = api_id or TELEGRAM_API_ID
        self.api_hash = api_hash or TELEGRAM_API_HASH
        self.client = None

    async def init_client(self):
        """Инициализация и запуск клиента Telegram через официальный MTProto прокси"""
        if not self.client or not self.client.is_connected():
            is_cloud = os.path.exists("/mount")

            if is_cloud:
                # Подключение напрямую (для облака Streamlit)
                self.client = TelegramClient(
                    SESSION_PATH,
                    int(self.api_id),
                    self.api_hash
                )
            else:
                # Подключение с вашим локальным прокси (для вашего компьютера)
                proxy_config = ("127.0.0.1", 1443, 'ddca074a3c7e2f247657714dd984879069')
                self.client = TelegramClient(
                    SESSION_PATH,
                    int(self.api_id),
                    self.api_hash,
                    connection=ConnectionTcpMTProxyRandomizedIntermediate,
                    proxy=proxy_config
                )

            await self.client.start()

    def extract_hr_contacts(self, text: str) -> list[str]:
        """Ищет контакты HR в тексте поста."""
        if not text:
            return []

        matches = re.findall(r'(?<!\w)@([A-Za-z0-9_]{5,32})', text)
        valid_contacts = []
        for match in matches:
            contact = f"@{match}"
            if contact not in valid_contacts:
                valid_contacts.append(contact)

        return valid_contacts

    async def fetch_channel_posts(self, channel_username: str, limit: int = 10) -> list[dict]:
        """Сканирует последние сообщения из указанного канала (для первичной загрузки)."""
        await self.init_client()
        posts = []

        try:
            channel_clean = channel_username.strip().replace("https://t.me/", "").replace("@", "")

            async for message in self.client.iter_messages(channel_clean, limit=limit):
                if message.text:
                    contacts = self.extract_hr_contacts(message.text)
                    posts.append({
                        "id": message.id,
                        "channel": channel_clean,
                        "text": message.text,
                        "date": message.date,
                        "contacts": contacts
                    })
        except Exception as e:
            print(f"Ошибка при чтении канала {channel_username}: {e}")

        return posts

    async def send_application(
            self,
            hr_username: str,
            message_text: str,
            file_path: str = None,
            channel: str = None,
            message_id: int = None
    ) -> bool:
        """Отправляет личное сообщение рекрутеру с пересылкой исходного поста и резюме."""
        await self.init_client()
        try:
            if channel and message_id:
                try:
                    await self.client.forward_messages(hr_username, message_id, channel)
                except Exception as f_err:
                    print(f"Не удалось переслать пост напрямую: {f_err}")

            if file_path:
                await self.client.send_file(
                    hr_username,
                    file_path,
                    caption=message_text
                )
            else:
                await self.client.send_message(hr_username, message_text)

            return True
        except Exception as e:
            print(f"Ошибка при отправке сообщения для @{hr_username}: {e}")
            return False

    async def close(self):
        """Безопасное закрытие сессии"""
        if self.client and self.client.is_connected():
            try:
                await self.client.disconnect()
            except Exception:
                pass