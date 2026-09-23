from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

import httpx

from ..config import settings


YANDEX_PUBLIC_API = "https://cloud-api.yandex.net/v1/disk/public/resources"
YANDEX_PUBLIC_DOWNLOAD_API = "https://cloud-api.yandex.net/v1/disk/public/resources/download"


@dataclass(frozen=True)
class YandexResource:
    name: str
    resource_type: str
    size: int | None
    mime_type: str | None
    modified: str | None
    public_url: str | None
    path: str | None


class YandexDiskClient:
    def __init__(self) -> None:
        self.client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0, connect=20.0),
            follow_redirects=True,
            headers={"User-Agent": "VITAGROUP-OEE/0.1"},
        )

    async def close(self) -> None:
        await self.client.aclose()

    async def metadata(
        self,
        public_url: str,
        resource_path: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "public_key": public_url,
            "limit": limit,
            "offset": offset,
        }
        if resource_path:
            params["path"] = resource_path

        response = await self.client.get(YANDEX_PUBLIC_API, params=params)
        response.raise_for_status()
        return response.json()

    async def list_folder(
        self,
        public_url: str,
        resource_path: str | None = None,
        *,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        payload = await self.metadata(
            public_url,
            resource_path,
            limit=limit,
            offset=offset,
        )
        embedded = payload.get("_embedded") or {}
        return embedded.get("items") or []

    async def download_link(
        self,
        public_url: str,
        resource_path: str | None = None,
    ) -> str:
        params: dict[str, Any] = {"public_key": public_url}
        if resource_path:
            params["path"] = resource_path

        response = await self.client.get(
            YANDEX_PUBLIC_DOWNLOAD_API,
            params=params,
        )
        response.raise_for_status()
        payload = response.json()
        href = payload.get("href")
        if not href:
            raise RuntimeError("Yandex Disk did not return a download link")
        return href

    async def download_bytes(
        self,
        public_url: str,
        resource_path: str | None = None,
    ) -> bytes:
        href = await self.download_link(public_url, resource_path)
        response = await self.client.get(href)
        response.raise_for_status()
        return response.content


def configured_plan_source() -> tuple[str, str | None]:
    public_url = settings.yandex_plan_public_url.strip()
    if not public_url:
        raise RuntimeError("YANDEX_PLAN_PUBLIC_URL is not configured")
    resource_path = settings.yandex_plan_resource_path.strip() or None
    return public_url, resource_path


def public_key_hash(public_url: str) -> str:
    return hashlib.sha256(public_url.encode("utf-8")).hexdigest()
