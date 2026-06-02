"""Configuração dos workers (lida do ambiente)."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str
    anthropic_api_key: str | None = None
    go_upc_api_key: str | None = None
    serpapi_key: str | None = None
    icecat_username: str | None = None
    awin_feed_url: str | None = None

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL não definido (ver workers/.env.example).")
        return cls(
            database_url=database_url,
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY"),
            go_upc_api_key=os.environ.get("GO_UPC_API_KEY"),
            serpapi_key=os.environ.get("SERPAPI_KEY"),
            icecat_username=os.environ.get("ICECAT_USERNAME"),
            awin_feed_url=os.environ.get("AWIN_FEED_URL"),
        )
