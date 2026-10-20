"""Backtest Top N del S&P 500 (Point-in-Time), comparación de plazos y sensibilidad al calendario de arranque.

Cada N meses se compran, con ponderación igual, las N acciones del S&P 500 que más subieron en los últimos N meses.
Todo se guarda en SQLite y, al terminar, se actualiza el JSON que lee el frontend.
"""
import argparse
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

from top3 import errors as E
from top3.analysis import Context
from top3.config import DataSettings, load_config
from top3.console import configure_console
from top3.constituents import Constituents, ensure_constituents
from top3.db import open_db
from top3.logs import log, log_config, setup_logging
from top3.prices import ensure_prices, load_prices
from top3.report_data import export_report
from top3.universe import label
from top3.workflow import UniverseBuilder, run_offsets, run_single, run_sweep


def parse_args(argv=None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Backtest Top N S&P 500 (Point-in-Time) con caché SQLite")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--no-cache", action="store_true",
                    help="Ignora la información guardada hoy y vuelve a descargar todo")
    ap.add_argument("--sweep", action="store_true",
                    help="Simula varios plazos (config [simulation] months) y compara el retorno final")
    ap.add_argument("--months", type=int, default=None, metavar="N",
                    help="Plazo del backtest normal en meses (default: [backtest] months del config)")
    ap.add_argument("--offsets", action="store_true",
                    help="Para cada plazo de --sweep prueba todos los calendarios de arranque posibles "
                         "y reporta mediana y rango (mide cuánto es azar de calendario)")
    ap.add_argument("--large-cap", action="store_true",
                    help="Universo solo large-cap + mega-cap (config [universe] min_cap_billions); "
                         "el reporte HTML lleva el sufijo _largecap")
    ap.add_argument("--min-cap-billions", type=float, default=None, metavar="N",
                    help="Como --large-cap pero con otro umbral de capitalización (miles de millones de US$); "
                         "por ejemplo 200 = mega-cap")
    ap.add_argument("--years", type=float, default=None, metavar="N",
                    help="Corre un único período de N años (default: todos los de [backtest] periods_years)")
    return ap.parse_args(argv)


def resolve_periods(bt_cfg: dict, end_date: pd.Timestamp, years: float | None) -> list[tuple[float, pd.Timestamp]]:
    """Períodos a evaluar como (años, fecha de inicio). Un start_date explícito en el config es un único período."""
    if bt_cfg["start_date"]:
        start = pd.to_datetime(bt_cfg["start_date"])
        return [(round((end_date - start).days / 365.25, 1), start)]
    years_list = [years] if years else [float(y) for y in bt_cfg["periods_years"]]
    return [(y, end_date - pd.DateOffset(years=int(y))) for y in sorted(years_list)]


def resolve_levels(args: argparse.Namespace, cfg: dict) -> list[float]:
    """Umbrales de capitalización a correr (0 = índice completo)."""
    if args.large_cap or args.min_cap_billions is not None:
        return [args.min_cap_billions if args.min_cap_billions is not None
                else float(cfg["universe"]["min_cap_billions"])]
    if args.sweep:  # --sweep sin filtro explícito: todos los universos configurados
        return [float(x) for x in cfg["universe"]["sweep_min_cap_billions"]]
    return [0.0]


def run(args: argparse.Namespace, cfg: dict) -> list[Path]:
    """Actualiza los datos y corre el backtest de cada período; devuelve los reportes HTML generados."""
    use_cache = not args.no_cache
    log.info("Caché: %s", "activada (se reutiliza lo descargado hoy)" if use_cache else "DESACTIVADA (--no-cache)")
    bt_cfg = cfg["backtest"]
    settings = DataSettings.from_config(cfg)

    today = date.today()
    history_start = (today - timedelta(days=round(float(cfg["data"]["history_years"]) * 365.25))).isoformat()
    price_end = (today + timedelta(days=1)).isoformat()  # yfinance: end exclusivo

    end_date = pd.to_datetime(bt_cfg["end_date"] or today)
    periods = resolve_periods(bt_cfg, end_date, args.years)
    for years, start_date in periods:
        if start_date >= end_date:
            raise SystemExit(E.CFG_BAD_DATES.msg(
                f"start_date ({start_date.date()}) debe ser anterior a end_date ({end_date.date()})"))
        log.info("Histórico: %s a %s | Backtest de %g años: %s a %s", history_start, today, years,
                 start_date.date(), end_date.date())
        if start_date < pd.to_datetime(history_start):
            log.warning(E.CFG_SHORT_HISTORY.msg("El inicio del backtest de %g años (%s) es anterior al histórico descargado (%s); "
                                            "subí [data] history_years"), years, start_date.date(), history_start)

    conn = open_db(cfg["data"]["db_path"])
    try:
        ensure_constituents(conn, settings, use_cache)
        constituents = Constituents(conn, cfg["tickers"]["aliases"])
        tickers = constituents.all_between(history_start, today)
        log.info("Tickers únicos que pasaron por el S&P 500 en el histórico: %d", len(tickers))

        ensure_prices(conn, tickers, history_start, price_end, use_cache, settings)
        prices = load_prices(conn)

        levels = resolve_levels(args, cfg)
        build_universe = UniverseBuilder(conn, prices, use_cache, settings)
        months = args.months or int(bt_cfg["months"])

        reports: list[Path] = []
        for years, start_date in periods:
            # Cada período lleva su propio config (años) y sufijo de los HTML (_5y, _10y...)
            ctx = Context(conn, {**cfg, "backtest": {**bt_cfg, "backtest_years": years}}, settings, constituents,
                          prices, start_date, end_date, use_cache, file_suffix=f"_{years:g}y")
            log.info("########## Período: %g años (%s a %s) ##########", years, start_date.date(), end_date.date())
            for level in levels:
                universe = build_universe(level)
                if args.sweep:
                    log.info("##### Sweep - universo: %s #####", label(level))
                    reports += run_sweep(ctx, universe)
                elif args.offsets:
                    reports.append(run_offsets(ctx, universe))
                else:
                    reports.append(run_single(ctx, months, universe))
    finally:
        conn.close()
    return reports


def main(argv=None) -> None:
    args = parse_args(argv)
    configure_console()
    cfg = load_config(args.config)
    setup_logging(cfg["output"]["backtest_log"], cfg["output"]["log_dir"])
    log_config(cfg, args.config)

    reports = run(args, cfg)
    if args.sweep or args.offsets:
        print("\nReportes HTML generados:")
        for path in reports:
            print(f"  {path}")
    export_report(cfg)


if __name__ == "__main__":
    main()
