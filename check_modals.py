# -*- coding: utf-8 -*-
"""Проверка лимитов Discord на поля модалок.

Discord валидирует label ТОЛЬКО при отправке формы — из-за этого бот
молча получает 400 Invalid Form Body, а пользователь видит «не ответило
вовремя». Запускать перед пушем:  python -X utf8 check_modals.py
"""

import inspect

import discord

import cogs.tickets as mod

LIMIT_LABEL = 45
LIMIT_PLACEHOLDER = 100


def main() -> int:
    problems = 0
    for name, obj in vars(mod).items():
        if not inspect.isclass(obj) or not issubclass(obj, discord.ui.Modal):
            continue
        if obj is discord.ui.Modal:
            continue
        try:
            modal = obj()
        except TypeError:
            continue  # модалка требует аргументов в конструкторе
        for child in modal.children:
            data = child.to_dict()
            label = data.get("label", "") or ""
            placeholder = data.get("placeholder", "") or ""
            if not 1 <= len(label) <= LIMIT_LABEL:
                print(f"[!] {name}: label {len(label)} символов (макс {LIMIT_LABEL}): {label!r}")
                problems += 1
            if len(placeholder) > LIMIT_PLACEHOLDER:
                print(f"[!] {name}: placeholder {len(placeholder)} символов (макс {LIMIT_PLACEHOLDER})")
                problems += 1

    if problems:
        print(f"Проблем: {problems}")
    else:
        print("OK: все label и placeholder в лимитах")
    return problems


if __name__ == "__main__":
    raise SystemExit(1 if main() else 0)
