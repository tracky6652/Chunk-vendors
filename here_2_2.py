# -*- coding: utf-8 -*-


import os
import sys
import asyncio
import logging

from telethon import TelegramClient, events
from telethon.tl import types
from telethon.sessions import StringSession



# Credentials
TG_API_ID = os.environ.get("TG_API_ID", "23547930")
TG_API_HASH = os.environ.get("TG_API_HASH", "03c0cd64a8bd77c43842482e70be0ee8")
TG_PHONE = os.environ.get("TG_PHONE", "+2349023111538")
TG_PASSWORD = os.environ.get("TG_PASSWORD", "")
TG_SESSION_STRING = os.environ.get("TG_SESSION_STRING", "")

 # Forwarding Settings
SOURCE_CHAT = os.environ.get("SOURCE_CHAT", "-1002564377166")
TARGET_CHAT = os.environ.get("TARGET_CHAT", "-1003710633412")
SECOND_TARGET_CHAT = os.environ.get("SECOND_TARGET_CHAT", "-5078829607")
FORWARD_MODE = os.environ.get("FORWARD_MODE", "copy")  # 'copy' or 'forward'
FILTER_FROM_USERNAME = os.environ.get("FILTER_FROM_USERNAME", "") # e.g., 'some_user'. Leave empty to disable.
SKIP_SERVICE_MESSAGES = os.environ.get("SKIP_SERVICE_MESSAGES", "true") # 'true' or 'false'

 # Logging
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


def parse_bool(s: str) -> bool:
    return str(s).strip().lower() in ("1", "true", "yes", "y", "on")

def parse_entity_spec(s: str):
    v = s.strip()
    if v.lstrip("-").isdigit():
        try:
            return int(v)
        except Exception:
            pass
    return v

class TelegramForwarder:
    def __init__(self):
        self.api_id = int(TG_API_ID)
        self.api_hash = TG_API_HASH
        self.phone = TG_PHONE
        self.password = TG_PASSWORD if TG_PASSWORD else None
        self.session_string = TG_SESSION_STRING

        self.forward_mode = FORWARD_MODE.strip().lower()
        self.filter_from_username = FILTER_FROM_USERNAME.strip().lstrip("@").lower()
        self.skip_service_messages = parse_bool(SKIP_SERVICE_MESSAGES)

        logging.basicConfig(
            level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(message)s"
        )
        self.client = None
        self.source_entity = None
        self.target_entity = None
        self.target_entities = []

    async def _login(self):
        if self.session_string:
            self.client = TelegramClient(StringSession(self.session_string), self.api_id, self.api_hash)
            await self.client.start()
            logging.info("Using session string.")
        else:
            self.client = TelegramClient("forwarder", self.api_id, self.api_hash)

            async def code_callback():
                code = input("Enter the login code Telegram sent to you: ")
                return code.strip()

            # auto-supplies password without asking if available
            await self.client.start(
                phone=lambda: self.phone,
                code_callback=code_callback,
                password=lambda: self.password if self.password else None
            )
            logging.info("Logged in using phone.")

    async def _get_entities(self):
        self.source_entity = await self.client.get_input_entity(parse_entity_spec(SOURCE_CHAT))
        self.target_entity = await self.client.get_input_entity(parse_entity_spec(TARGET_CHAT))
        self.target_entities = [self.target_entity]

        second_chat = SECOND_TARGET_CHAT.strip()
        if second_chat:
            try:
                second_entity = await self.client.get_input_entity(parse_entity_spec(second_chat))
                self.target_entities.append(second_entity)
            except Exception:
                logging.exception(f"Failed to get second target entity for {SECOND_TARGET_CHAT}")

    async def _on_new_message(self, event):
        m = event.message

        if self.skip_service_messages and isinstance(m, types.MessageService):
            return

        if self.filter_from_username:
            sender = await event.get_sender()
            username = (getattr(sender, "username", None) or "").lower()
            if username != self.filter_from_username:
                return

        targets = getattr(self, "target_entities", None) or [self.target_entity]

        try:
            if self.forward_mode == "forward":
                for target in targets:
                    await m.forward_to(target)
                logging.info(f"Forwarded: {m.id}")
            else:
                if m.media:
                    data = None
                    for target in targets:
                        try:
                            await self.client.send_file(
                                target,
                                m.media,
                                caption=m.message or None,
                                formatting_entities=m.entities
                            )
                            logging.info(f"Copied media: {m.id}")
                        except Exception as e:
                            logging.warning(f"Direct media copy failed for message {m.id}: {e}. Attempting re-upload.")
                            try:
                                if data is None:
                                    # Download media to bytes and re-upload
                                    data = await m.download_media(file=bytes)
                                if data:
                                    await self.client.send_file(
                                        target, data,
                                        caption=m.message or None,
                                        formatting_entities=m.entities
                                    )
                                    logging.info(f"Re-uploaded & copied: {m.id}")
                                else:
                                    logging.warning(f"No data downloaded for media message {m.id}. Skipping.")
                            except Exception:
                                logging.exception(f"Media re-upload copy failed for message {m.id}")
                else:
                    for target in targets:
                        await self.client.send_message(
                            target,
                            m.message or "",
                            formatting_entities=m.entities
                        )
                        logging.info(f"Copied: {m.id}")

        except Exception:
            logging.exception(f"Send failed for message {m.id}")

    async def run(self):
        await self._login()
        await self._get_entities()

        self.client.add_event_handler(self._on_new_message, events.NewMessage(chats=self.source_entity))

        logging.info(f"Forwarding from {SOURCE_CHAT} \u2192 {TARGET_CHAT}")
        await self.client.run_until_disconnected()


if __name__ == "__main__":
    try:
        forwarder = TelegramForwarder()
        asyncio.run(forwarder.run())
    except KeyboardInterrupt:
        logging.info("Forwarder stopped by user.")
    except Exception as e:
        logging.exception("An unexpected error occurred.")