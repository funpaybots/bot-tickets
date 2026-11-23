# -*- coding: utf-8 -*-
"""Проверка оценок хелперов в тикетах (временная папка data)."""

import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="ratings_check_")
sys.path.insert(0, r"C:\Users\tomoe\Downloads\bot-tickets")

import storage
storage.DATA_DIR = os.path.join(TMP, "data")

from cogs import tickets as tc

fails = []


def check(name, cond, extra=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


G, T = 555, 100500

# Сохранение оценки
check("first rating saved", tc._save_rating(G, T, 777, 5, 42))
check("double rating blocked", not tc._save_rating(G, T, 777, 1, 42))
check("second ticket ok", tc._save_rating(G, T + 1, 777, 4, 43))
check("third ticket other helper", tc._save_rating(G, T + 2, 888, 3, 44))

# Сводка
rows = tc._ratings_summary(G)
d = {hid: (avg, cnt) for hid, avg, cnt in rows}
check("summary helper 777", abs(d[777][0] - 4.5) < 0.01 and d[777][1] == 2, str(d.get(777)))
check("summary helper 888", d[888][0] == 3.0 and d[888][1] == 1, str(d.get(888)))
check("summary sorted", rows[0][0] == 777, str(rows))

# Мусор не падает и не считается
from storage import load, save
data = load(tc.RATINGS_FILE, {})
data.setdefault(str(G), {})["bad"] = {"helper_id": "abc", "stars": 5}
data[str(G)]["bad2"] = {"helper_id": 777, "stars": 99}
save(tc.RATINGS_FILE, data)
rows = tc._ratings_summary(G)
d = {hid: (avg, cnt) for hid, avg, cnt in rows}
check("garbage ignored", d[777][1] == 2, str(d.get(777)))

# Другая гильдия не смешивается
check("guild isolation", tc._ratings_summary(999) == [])

# Вьюха и custom_id
view = tc.RatingView(G, T, 42, 777)._arm_custom_ids()
check("view buttons", len(view.children) == 5)
check("custom ids", [c.custom_id for c in view.children] == [f"trate_{T}_{i}" for i in range(1, 6)])

# Реарм после рестарта: закрытый отвеченный тикет без оценки
save(tc.TICKETS_FILE, {
    str(G): {
        str(T + 20): {"open": False, "user_id": 42, "answered_by_id": 777},
        str(T + 9): {"open": True, "user_id": 42, "answered_by_id": 777},
        str(T + 10): {"open": False, "user_id": 42},  # без ответа
        str(T + 11): {"open": False, "user_id": "oops", "answered_by_id": 777},  # мусор
    }
})

import asyncio

import discord
from discord.ext import commands


async def main():
    bt = commands.Bot(command_prefix="!", intents=discord.Intents.default())
    await bt.load_extension("cogs.tickets")
    names = {c.name for c in bt.tree.get_commands()}
    check("commands", {"close", "tickets", "ticket_ratings", "setup_tickets"} <= names, str(sorted(names)))
    tc._rearm_rating_views(bt)
    armed = sum(1 for v in bt.persistent_views if isinstance(v, tc.RatingView))
    check("rearm exactly one", armed == 1, str(armed))
    await bt.unload_extension("cogs.tickets")
    return bt


asyncio.run(main())

# Кириллица
check("cyrillic ok", "Оценка" in tc._rating_embed("Кекс").description or "Оцени" in tc._rating_embed("Кекс").description)

import re
t = open("cogs/tickets.py", encoding="utf-8").read()
cjk = len(re.findall(r"[\u3040-\u30ff\u3400-\u4dbf\u4e00-\u9fff\uac00-\ud7af]", t))
check("no CJK", cjk == 0, str(cjk))

print(f"\nВсего провалов: {len(fails)}")
if fails:
    print("Провалились: " + ", ".join(fails))
sys.exit(1 if fails else 0)
