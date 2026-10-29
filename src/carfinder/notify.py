"""Optional Telegram alerts for new listings.

Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID (as GitHub Actions secrets) to enable.
"""

from __future__ import annotations

import html
import os

import httpx

from carfinder.store import SearchResult

MAX_PER_MESSAGE = 10


def format_message(result: SearchResult) -> str | None:
    new = result.new_listings
    if not new:
        return None
    lines = [f"<b>{html.escape(result.query.title)}</b>: {len(new)} new"]
    for car in new[:MAX_PER_MESSAGE]:
        facts = " · ".join(
            str(p)
            for p in (
                f"€{car.price_eur:,}",
                car.year,
                f"{car.mileage_km:,} km" if car.mileage_km else None,
                car.city,
                f"score {car.score}" if car.score is not None else None,
            )
            if p
        )
        lines.append(f'• <a href="{html.escape(car.url)}">{html.escape(car.title)}</a>\n  {html.escape(facts)}')
    if len(new) > MAX_PER_MESSAGE:
        lines.append(f"…and {len(new) - MAX_PER_MESSAGE} more")
    return "\n".join(lines)


def send_telegram(client: httpx.Client, result: SearchResult) -> bool:
    token = os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID")
    text = format_message(result)
    if not (token and chat_id and text):
        return False
    client.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
    ).raise_for_status()
    return True
