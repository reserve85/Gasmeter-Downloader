"""Translator (en/de) with locale-aware number and date formatting."""

from __future__ import annotations

from typing import Any

_EN: dict[str, str] = {
    "app.title": "Gasmeter Downloader",
    "menu.file": "&File",
    "menu.download_missing": "Download missing logfiles",
    "menu.import_archive": "Import logfiles…",
    "menu.settings": "Settings…",
    "menu.check_updates": "Check for updates…",
    "menu.language": "&Language",
    "menu.exit": "Exit",
    "main.tab.table": "Table",
    "main.tab.charts": "Charts",
    "status.ready": "Ready",
    "status.syncing": "Syncing logfiles…",
    "status.synced": "Sync complete: {downloaded} downloaded, {missing} missing on device, {failed} failed",
    "status.updating": "Checking for updates…",
    "table.date": "Date",
    "table.import_value": "Import",
    "table.interpolated_value": "Interpolated",
    "table.modified_value": "Modified",
    "table.source": "Source",
    "table.restore": "Restore",
    "table.filter_from": "From",
    "table.filter_to": "To",
    "table.filter_preset": "Preset",
    "table.filter_all": "All",
    "table.filter_30d": "Last 30 days",
    "table.filter_90d": "Last 90 days",
    "table.filter_year": "This year",
    "source.logfile": "logfile",
    "source.interpolated": "interpolated",
    "source.manual": "manual",
    "manual.title": "Edit reading",
    "manual.date_label": "Date",
    "manual.import_label": "Import value",
    "manual.interpolated_label": "Interpolated value",
    "manual.modified_label": "Modified value (m³)",
    "manual.info": "Only the Modified value can be edited. Import and interpolated values are shown for reference and are never overwritten.",
    "manual.ok": "Save",
    "manual.cancel": "Cancel",
    "settings.title": "Settings",
    "settings.device_ip": "Device IP",
    "settings.max_days": "Download window (days)",
    "settings.language": "Language",
    "settings.lang_auto": "Automatic",
    "settings.unit": "Default unit",
    "settings.paths": "Storage",
    "settings.paths.download": "Download folder",
    "settings.paths.archive": "Archive folder",
    "settings.paths.database": "Database file",
    "settings.browse": "Browse…",
    "settings.gas_header": "Gas parameters (calorific value / Z-number per date)",
    "settings.valid_from": "Valid from",
    "settings.valid_to": "Valid to",
    "settings.add_interval": "Add / Edit interval",
    "settings.delete_interval": "Delete selected",
    "settings.calorific": "Calorific value (kWh/m³)",
    "settings.z_value": "Z value",
    "settings.defaults_from": "Defaults for seed/new intervals: cal {cal}, z {z}",
    "settings.token": "GitHub token (optional)",
    "settings.ok": "OK",
    "settings.cancel": "Cancel",
    "settings.invalid": "Invalid settings: {errors}",
    "charts.kpi.total": "Total",
    "charts.kpi.avg_day": "Avg / day",
    "charts.kpi.max_day": "Max day",
    "charts.kpi.interpolated": "Interpolated days",
    "charts.kpi.latest": "Latest meter",
    "charts.meter.title": "Meter reading",
    "charts.usage.title": "Usage",
    "charts.monthly.title": "Monthly",
    "charts.agg.daily": "Daily",
    "charts.agg.weekly": "Weekly",
    "charts.agg.monthly": "Monthly",
    "charts.unit_m3": "m³",
    "charts.unit_kwh": "kWh",
    "charts.yoy": "Previous year",
    "charts.trend": "Trend",
    "charts.from": "From",
    "charts.to": "To",
    "charts.empty": "No data for the selected period.",
    "update.title": "Update",
    "update.check": "Check for updates",
    "update.download_apply": "Download & apply",
    "update.close": "Close",
    "update.checking": "Checking…",
    "update.up_to_date": "You are up to date (version {version}).",
    "update.available": "A new version is available: {version}.",
    "update.error": "Update check failed: {error}",
    "update.restarted": "Update installed. Please restart the application.",
    "log.title": "Log",
    "log.clear": "Clear",
    "msg.sync_failed": "Sync failed: {error}",
    "msg.invalid_value": "Please enter a valid non-negative number.",
    "msg.choose_files": "Choose logfiles",
    "msg.no_files": "No files selected.",
}
_DE: dict[str, str] = {
    "app.title": "Gasmeter-Downloader",
    "menu.file": "&Datei",
    "menu.download_missing": "Fehlende Logdateien herunterladen",
    "menu.import_archive": "Logdateien importieren…",
    "menu.settings": "Einstellungen…",
    "menu.check_updates": "Nach Updates suchen…",
    "menu.language": "&Sprache",
    "menu.exit": "Beenden",
    "main.tab.table": "Tabelle",
    "main.tab.charts": "Diagramme",
    "status.ready": "Bereit",
    "status.syncing": "Logdateien werden synchronisiert…",
    "status.synced": "Sync abgeschlossen: {downloaded} geladen, {missing} fehlen am Gerät, {failed} fehlgeschlagen",
    "status.updating": "Suche nach Updates…",
    "table.date": "Datum",
    "table.import_value": "Import",
    "table.interpolated_value": "Interpoliert",
    "table.modified_value": "Korrigiert",
    "table.source": "Quelle",
    "table.restore": "Wiederherstellen",
    "table.filter_from": "Von",
    "table.filter_to": "Bis",
    "table.filter_preset": "Zeitraum",
    "table.filter_all": "Alle",
    "table.filter_30d": "Letzte 30 Tage",
    "table.filter_90d": "Letzte 90 Tage",
    "table.filter_year": "Dieses Jahr",
    "source.logfile": "Logdatei",
    "source.interpolated": "interpoliert",
    "source.manual": "manuell",
    "manual.title": "Zählerstand bearbeiten",
    "manual.date_label": "Datum",
    "manual.import_label": "Importwert",
    "manual.interpolated_label": "Interpolierter Wert",
    "manual.modified_label": "Korrigierter Wert (m³)",
    "manual.info": "Nur der korrigierte Wert ist editierbar. Import- und interpolierte Werte werden nur angezeigt und nie überschrieben.",
    "manual.ok": "Speichern",
    "manual.cancel": "Abbrechen",
    "settings.title": "Einstellungen",
    "settings.device_ip": "Geräte-IP",
    "settings.max_days": "Download-Zeitraum (Tage)",
    "settings.language": "Sprache",
    "settings.lang_auto": "Automatisch",
    "settings.unit": "Standard-Einheit",
    "settings.paths": "Speicherorte",
    "settings.paths.download": "Download-Ordner",
    "settings.paths.archive": "Archiv-Ordner",
    "settings.paths.database": "Datenbank-Datei",
    "settings.browse": "Durchsuchen…",
    "settings.gas_header": "Gasparameter (Brennwert / Z-Zahl je Zeitraum)",
    "settings.valid_from": "Gültig von",
    "settings.valid_to": "Gültig bis",
    "settings.add_interval": "Intervall hinzufügen / bearbeiten",
    "settings.delete_interval": "Auswahl löschen",
    "settings.calorific": "Brennwert (kWh/m³)",
    "settings.z_value": "Z-Zahl",
    "settings.defaults_from": "Standardwerte für neues/Seed-Intervall: cal {cal}, z {z}",
    "settings.token": "GitHub-Token (optional)",
    "settings.ok": "OK",
    "settings.cancel": "Abbrechen",
    "settings.invalid": "Ungültige Einstellungen: {errors}",
    "charts.kpi.total": "Gesamt",
    "charts.kpi.avg_day": "Ø / Tag",
    "charts.kpi.max_day": "Max. Tag",
    "charts.kpi.interpolated": "Interp. Tage",
    "charts.kpi.latest": "Letzter Stand",
    "charts.meter.title": "Zählerstand",
    "charts.usage.title": "Verbrauch",
    "charts.monthly.title": "Monatlich",
    "charts.agg.daily": "Täglich",
    "charts.agg.weekly": "Wöchentlich",
    "charts.agg.monthly": "Monatlich",
    "charts.unit_m3": "m³",
    "charts.unit_kwh": "kWh",
    "charts.yoy": "Vorjahr",
    "charts.trend": "Trend",
    "charts.from": "Von",
    "charts.to": "Bis",
    "charts.empty": "Keine Daten im gewählten Zeitraum.",
    "update.title": "Update",
    "update.check": "Nach Updates suchen",
    "update.download_apply": "Herunterladen & installieren",
    "update.close": "Schließen",
    "update.checking": "Suche läuft…",
    "update.up_to_date": "Sie sind aktuell (Version {version}).",
    "update.available": "Neue Version verfügbar: {version}.",
    "update.error": "Update-Prüfung fehlgeschlagen: {error}",
    "update.restarted": "Update installiert. Bitte starten Sie die Anwendung neu.",
    "log.title": "Protokoll",
    "log.clear": "Leeren",
    "msg.sync_failed": "Sync fehlgeschlagen: {error}",
    "msg.invalid_value": "Bitte einen gültigen, nicht-negativen Wert eingeben.",
    "msg.choose_files": "Logdateien wählen",
    "msg.no_files": "Keine Dateien gewählt.",
}

_CATALOGS = {"en": _EN, "de": _DE}

_GROUP_SEP = {"en": ",", "de": "."}
_DECIMAL_SEP = {"en": ".", "de": ","}
_DATE_FORMAT = {"en": "%Y-%m-%d", "de": "%d.%m.%Y"}


class Translator:
    """Simple dictionary-based translator. English is the fallback."""

    def __init__(self, language: str = "en"):
        self.set_language(language)

    def set_language(self, language: str) -> None:
        self._language = language if language in _CATALOGS else "en"

    @property
    def language(self) -> str:
        return self._language

    def t(self, key: str, **kwargs: Any) -> str:
        text = _CATALOGS[self._language].get(key) or _EN.get(key) or key
        if kwargs:
            text = text.format(**kwargs)
        return text

    def format_number(self, value, decimals: int = 3) -> str:
        if value is None:
            return "–"
        number = float(value) if not isinstance(value, float) else value
        number = round(number, decimals)
        group, decimal = _GROUP_SEP[self._language], _DECIMAL_SEP[self._language]
        formatted = f"{number:.{decimals}f}".replace(".", decimal)
        int_part, _, frac_part = formatted.partition(decimal)
        chunks = []
        while len(int_part) > 3:
            chunks.insert(0, int_part[-3:])
            int_part = int_part[:-3]
        chunks.insert(0, int_part)
        return group.join(chunks) + (decimal + frac_part if frac_part else "")

    def format_date(self, d) -> str:
        return d.strftime(_DATE_FORMAT[self._language])
