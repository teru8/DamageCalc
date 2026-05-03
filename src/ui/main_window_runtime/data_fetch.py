from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from PyQt5.QtWidgets import QMessageBox

from src.data import database as db
from src.data.pokeapi_client import PokeApiLoader


@dataclass
class DataFetchManager:
    """Coordinate MainWindow data-fetch worker startup and guard checks."""

    def start_pokeapi_fetch(self, window: Any, safe_disconnect: Callable[..., None]) -> None:
        if window._api_loader and window._api_loader.isRunning():
            return
        safe_disconnect(window._api_loader, window._api_loader.progress, window._api_loader.finished)
        window._api_loader = PokeApiLoader()
        window._api_loader.progress.connect(window._on_api_progress)
        window._api_loader.finished.connect(window._on_api_done)
        window._set_fetch_buttons_enabled(False)
        window._status_bar.showMessage("PokeAPIデータ取得を開始")
        window._log("PokeAPIデータ取得を開始")
        window._api_loader.start()

    def start_usage_fetch(
        self,
        window: Any,
        season: str,
        safe_disconnect: Callable[..., None],
        source: str | None = None,
    ) -> None:
        scraper_cls, usage_sources, usage_default, import_error = window._get_usage_scraper_symbols()
        if scraper_cls is None:
            QMessageBox.information(
                window,
                "使用率取得は利用不可",
                "usage_scraper の読み込みに失敗したため、この環境では使用率取得を実行できません。\n\n{}".format(import_error or ""),
            )
            return
        resolved_source = source if source else (
            window._option_source_combo.currentData() if window._option_source_combo else usage_default
        )
        db.set_active_usage_season(season)
        status = db.get_local_data_status(season)
        if status["species_count"] == 0 or status["move_count"] == 0:
            QMessageBox.information(
                window,
                "データ不足",
                "先に PokeAPI データを取得してください。",
            )
            return
        if window._scraper and window._scraper.isRunning():
            return
        safe_disconnect(window._scraper, window._scraper.progress, window._scraper.finished)
        window._scraper = scraper_cls(season=season, source=resolved_source)
        window._scraper.progress.connect(window._on_usage_progress)
        window._scraper.finished.connect(window._on_scraper_done)
        window._set_fetch_buttons_enabled(False)
        source_label = usage_sources.get(resolved_source, resolved_source)
        window._status_bar.showMessage("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
        window._log("使用率データ取得を開始 [{}] [{}]".format(season, source_label))
        window._scraper.start()
