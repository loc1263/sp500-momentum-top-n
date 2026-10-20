"""Pipeline completo: tests (opcional) -> backtest de todos los períodos y universos -> Top actual de cada universo
-> JSON del frontend.

    python run_pipeline.py                 # todo, con caché y descarga incremental de precios
    python run_pipeline.py --no-cache      # descarga todo de nuevo
    python run_pipeline.py --tests         # corre primero los tests
    python run_pipeline.py --skip-backtest # solo Top actual + export

Cada paso es un script independiente que se ejecuta en su propio proceso; si uno falla, el pipeline se corta.
Períodos, plazos y universos salen de config.toml ([backtest] periods_years, [simulation] months,
[universe] sweep_min_cap_billions).
"""
import argparse
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from top3.config import load_config
from top3.logs import STEP_ENV, SUMMARY_FILE_ENV, format_summary, merge_summaries, paint

HERE = Path(__file__).resolve().parent


def universe_args(level):
    """Argumentos de universo para los scripts: 0 = índice completo (sin filtro)."""
    return ["--min-cap-billions", f"{level:g}"] if level else []


def build_steps(cfg, args):
    py, config = sys.executable, ["--config", args.config]
    pending = ["--no-cache"] if args.no_cache else []

    def cache():
        """--no-cache solo para el primer paso que descarga: los siguientes reutilizan lo que ese paso acaba de
        guardar en SQLite en vez de volver a bajar lo mismo (los Top actual repetían 3 veces las descargas)."""
        flags = list(pending)
        pending.clear()
        return flags
    levels = [float(x) for x in cfg["universe"]["sweep_min_cap_billions"]]
    steps = []
    if args.tests:
        steps.append(("Tests", [py, "-m", "pytest", "-q"]))
    if not args.skip_backtest:
        years = ["--years", f"{args.years:g}"] if args.years else []
        steps.append(("Backtest: períodos x plazos x universos (sweep + offsets)",
                      [py, "top3_backtest.py", "--sweep", *config, *cache(), *years]))
    if not args.skip_actual:
        for level in levels:
            name = f"Top actual - {'índice completo' if not level else f'cap. >= US$ {level:g} B'}"
            steps.append((name, [py, "top3_actual.py", *config, *cache(), *universe_args(level)]))
    if not args.skip_etf:
        steps.append(("Ranking de ETFs de Vanguard", [py, "top3_etf.py", *config]))
    steps.append(("Exportar JSON del frontend", [py, "export_frontend.py", *config]))
    return steps


def main():
    ap = argparse.ArgumentParser(description="Corre el pipeline completo (backtest + Top actual + JSON del frontend)")
    ap.add_argument("--config", default="config.toml", help="Archivo de configuración (default: config.toml)")
    ap.add_argument("--no-cache", action="store_true", help="Vuelve a descargar todo en lugar de actualizar")
    ap.add_argument("--years", type=float, default=None, metavar="N",
                    help="Backtest de un único período de N años (default: todos los de periods_years)")
    ap.add_argument("--tests", action="store_true", help="Corre los tests antes del pipeline")
    ap.add_argument("--skip-backtest", action="store_true", help="Omite el backtest")
    ap.add_argument("--skip-actual", action="store_true", help="Omite el Top actual")
    ap.add_argument("--skip-etf", action="store_true", help="Omite el ranking de ETFs de Vanguard")
    args = ap.parse_args()

    cfg = load_config(args.config)
    steps = build_steps(cfg, args)
    print(f"Pipeline: {len(steps)} pasos\n")

    summary_file = Path(tempfile.mkdtemp()) / "summary.jsonl"  # cada paso deja ahí sus avisos y errores
    results, t_start = [], time.time()
    for i, (name, cmd) in enumerate(steps, 1):
        print("=" * 78)
        print(f"[{i}/{len(steps)}] {name}")
        print("=" * 78, flush=True)
        t0 = time.time()
        env = {**os.environ, SUMMARY_FILE_ENV: str(summary_file), STEP_ENV: name}
        rc = subprocess.run(cmd, cwd=HERE, env=env).returncode
        results.append((name, rc, time.time() - t0))
        if rc:
            print(paint(f"\nFALLÓ el paso «{name}» (código {rc}). Se corta el pipeline.", logging.ERROR),
                  file=sys.stderr)
            break

    print("\n" + "=" * 78)
    print("RESUMEN")
    print("=" * 78)
    for name, rc, secs in results:
        print(f"  {'OK   ' if not rc else 'FALLÓ'}  {secs:6.0f} s  {name}")
    for name, _ in steps[len(results):]:
        print(f"  omitido         {name}")
    print(f"\nTotal: {time.time() - t_start:.0f} s")
    items = merge_summaries(summary_file)
    if items:
        print("\n" + "\n".join(format_summary(items, str(Path(cfg["output"]["log_dir"]) / "*.log"))),
              file=sys.stderr)
    sys.exit(1 if any(rc for _, rc, _ in results) else 0)


if __name__ == "__main__":
    main()
