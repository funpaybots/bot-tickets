# -*- coding: utf-8 -*-
"""Проверка выгрузки истории тикета в файл при закрытии."""

import asyncio
import datetime
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="transcript_check_")
sys.path.insert(0, r"C:\Users\tomoe\Downloads\bot-tickets")

import storage
storage.DATA_DIR = os.path.join(TMP, "data")

from cogs import tickets as tc

fails = []


def check(name, cond, extra=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


class _Author:
    def __init__(self, name, uid):
        self.display_name = name
        self.id = uid


class _Att:
    def __init__(self, filename, url):
        self.filename = filename
        self.url = url


class _Embed:
    def __init__(self, title=None, description=None):
        self.title = title
        self.description = description


class _Msg:
    def __init__(self, name, uid, content, minute=0, attachments=(), embeds=(), stickers=()):
        self.author = _Author(name, uid)
        self.content = content
        self.system_content = content
        self.created_at = datetime.datetime(2026, 11, 26, 15, minute, tzinfo=datetime.timezone.utc)
        self.attachments = list(attachments)
        self.embeds = list(embeds)
        self.stickers = list(stickers)


class _Channel:
    id = 100500
    name = "ticket-0042"

    def __init__(self, messages):
        self._messages = messages

    def history(self, limit=200):
        async def gen():
            for m in self._messages[:limit]:
                yield m
        return gen()


# Строка: текст, вложения, эмбеды
line = tc._transcript_line(_Msg("котик", 42, "привет"))
check("line has time", "[26.11.2026 15:00]" in line, line)
check("line has author", "котик (42)" in line, line)
check("line has text", line.endswith("привет"), line)

line = tc._transcript_line(
    _Msg("котик", 42, "", attachments=[_Att("screen.png", "https://cdn/x")],
         embeds=[_Embed(title="Заявка")])
)
check("line attachment", "screen.png" in line and "https://cdn/x" in line, line)
check("line embed", "[embed] Заявка" in line, line)

line = tc._transcript_line(_Msg("котик", 42, ""))
check("line empty marker", "[без текста]" in line, line)

# Файл: порядок от старых к новым, шапка, имя
msgs = [
    _Msg("хелпер", 7, "третий", minute=3),
    _Msg("котик", 42, "второй", minute=2),
    _Msg("котик", 42, "первый", minute=1),
]


async def main():
    info = {
        "user_id": "42",
        "created_at": "26.11.2026 14:00",
        "closed_at": "26.11.2026 16:00",
    }
    closer = _Author("модер", 7)
    tinfo = {"label": "Вопрос"}

    f, count = await tc._build_transcript(_Channel(msgs), info, closer, tinfo)
    check("file built", f is not None and count == 3, str(count))
    text = f.fp.getvalue().decode("utf-8")
    check("filename by channel id", f.filename == "ticket-100500.txt", f.filename)
    check("header type", "Тип: Вопрос" in text)
    check("header closer", "модер (7)" in text)
    check("oldest first", text.index("первый") < text.index("второй") < text.index("третий"))
    check("limit respected", text.count("Сообщений в выгрузке: 3") == 1)


asyncio.run(main())

print(f"\nВсего провалов: {len(fails)}")
if fails:
    print("Провалились: " + ", ".join(fails))
sys.exit(1 if fails else 0)
