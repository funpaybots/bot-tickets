# -*- coding: utf-8 -*-
"""Проверка принятия заявки: участник из кеша, из API и когда его нет вовсе.

Главный кейс — «не даёт принять заявку»: без интента members кеш гильдии
неполный, и get_member() возвращает None для тех, кто на сервере. Бот должен
дотягиваться до участника через fetch_member().

Запуск: python check_accept.py
"""

import asyncio
import os
import sys
import tempfile

TMP = tempfile.mkdtemp(prefix="accept_check_")
sys.path.insert(0, r"C:\Users\tomoe\Downloads\bot-tickets")

import storage
storage.DATA_DIR = os.path.join(TMP, "data")

from cogs import tickets as tc  # noqa: E402

fails = []


def check(name, cond, extra=""):
    print(("OK   " if cond else "FAIL ") + name + (f"  {extra}" if extra else ""))
    if not cond:
        fails.append(name)


class _Role:
    def __init__(self, rid, name):
        self.id = rid
        self.name = name


class _Member:
    def __init__(self, uid):
        self.id = uid
        self.mention = f"<@{uid}>"
        self.added = []
        self.dms = []

    async def add_roles(self, role, reason=None):
        self.added.append(role)

    async def send(self, embed=None, view=None):
        self.dms.append(embed)


class _Channel:
    def __init__(self, cid):
        self.id = cid
        self.sent = []

    async def send(self, **kwargs):
        self.sent.append(kwargs)


class _Guild:
    def __init__(self, cached=None, fetched=None):
        self._cached = cached
        self._fetched = fetched
        self.name = "Тестовый сервер"

    def get_member(self, uid):
        return self._cached

    async def fetch_member(self, uid):
        return self._fetched

    def get_role(self, rid):
        return self._role if rid else None


class _Resp:
    def __init__(self):
        self.deferred = False
        self.messages = []

    async def defer(self):
        self.deferred = True

    async def send_message(self, *args, **kwargs):
        self.messages.append(args[0] if args else kwargs.get("content", ""))


class _Followup:
    def __init__(self):
        self.messages = []

    async def send(self, *args, **kwargs):
        self.messages.append(args[0] if args else kwargs.get("content", ""))


class _Perms:
    administrator = True


class _User:
    def __init__(self, uid=7):
        self.id = uid
        self.roles = []
        self.guild_permissions = _Perms()
        self.mention = f"<@{uid}>"
        self.display_name = "модер"


class _Interaction:
    def __init__(self, guild, channel):
        self.guild = guild
        self.channel = channel
        self.user = _User()
        self.response = _Resp()
        self.followup = _Followup()


CHANNEL_ID = 500
APPLICANT_ID = 42

closed = []


async def _fake_close(channel, closer, interaction=None):
    closed.append((channel, closer))


tc._do_close = _fake_close


def _seed(role_name="Хелпер", uid=APPLICANT_ID):
    tc.save(
        tc.TICKETS_FILE,
        {
            str(CHANNEL_ID): {
                "open": True,
                "type": "staff_app",
                "user_id": uid,
                "fields": {"__role": role_name},
            }
        },
    )


def _run(guild):
    channel = _Channel(CHANNEL_ID)
    inter = _Interaction(guild, channel)
    asyncio.run(tc._accept_app(inter))
    return inter, channel


def _ticket():
    return tc.load(tc.TICKETS_FILE, {}).get(str(CHANNEL_ID), {})


# 1. Участника нет в кеше, но он на сервере — выдача должна пройти.
role = _Role(tc.ROLE_BY_NAME["Хелпер"], "Хелпер")
member = _Member(APPLICANT_ID)
guild = _Guild(cached=None, fetched=member)
guild._role = role
_seed()
closed.clear()
inter, channel = _run(guild)

check("cache miss: deferred", inter.response.deferred)
check("cache miss: role granted", member.added == [role], str(member.added))
check("cache miss: log embed", any("Заявка принята" in (kw.get("embed").title or "")
                                  for kw in channel.sent if kw.get("embed")), str(len(channel.sent)))
check("cache miss: dm sent", len(member.dms) == 1)
check("cache miss: decision saved", _ticket().get("decision") == "accepted")
check("cache miss: ticket closed", len(closed) == 1)

# 2. Участника нет ни в кеше, ни в API — внятная ошибка, тикет открыт.
guild = _Guild(cached=None, fetched=None)
guild._role = role
_seed()
closed.clear()
inter, channel = _run(guild)

check("missing: deferred", inter.response.deferred)
check("missing: explains why", any("Не нашёл участника" in text for text in inter.followup.messages),
      str(inter.followup.messages))
check("missing: ticket stays open", _ticket().get("open") is True)
check("missing: not closed", not closed)

# 3. Роль не нашлась — понятная ошибка вместо падения.
guild = _Guild(cached=_Member(APPLICANT_ID), fetched=None)
guild._role = None
_seed(role_name="Хелпер")
closed.clear()
inter, channel = _run(guild)

check("no role: deferred", inter.response.deferred)
check("no role: explains", any("Не нашёл роль" in text for text in inter.followup.messages),
      str(inter.followup.messages))
check("no role: ticket stays open", _ticket().get("open") is True)

print()
if fails:
    print(f"Провалов: {len(fails)}")
    sys.exit(1)
print("Всего провалов: 0")
