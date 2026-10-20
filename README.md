# sp500-momentum-top-n - Top N del S&P 500

Estrategia de momentum: cada N meses se compran, con ponderación igual, las N acciones del S&P 500
que más subieron en los últimos N meses. Este proyecto la prueba con datos históricos (backtest),
mide cuánto del resultado depende del azar del calendario y genera reportes en consola y HTML.

> **Aviso:** es una herramienta de análisis, no una recomendación de inversión. El backtest no incluye
> comisiones ni impuestos y tiene sesgos de datos (ver [Limitaciones](docs/como-funciona.md#limitaciones)).

## Inicio rápido

Requiere Python 3.11 o superior y Node.js.

```
cd backend
pip install -r requirements.txt          # o requirements-dev.txt para correr también los tests
python run_pipeline.py                   # descarga datos, corre el backtest y el Top actual
cd ../frontend
npm install
cd ..
.\start.ps1                              # backend en :8000, frontend en http://localhost:5173
```

`lxml` lo necesita `pandas.read_html` para leer las tablas de Wikipedia.

## Estructura

```
start.ps1      # levanta backend + frontend
backend/       # Python: backtest, Top actual, base SQLite y API HTTP
frontend/      # SPA en Svelte 5 + Vite con los resultados del día y del backtest
docs/          # documentación
```

## Documentación

| Documento | Contenido |
|---|---|
| [docs/uso.md](docs/uso.md) | Comandos, pipeline completo, modos del backtest y Top actual |
| [docs/como-funciona.md](docs/como-funciona.md) | Metodología, universo y capitalización, limitaciones |
| [docs/configuracion.md](docs/configuracion.md) | Todas las claves de `config.toml` |
| [docs/salidas.md](docs/salidas.md) | Reportes HTML, consola, tablas SQLite y logs |
| [docs/errores.md](docs/errores.md) | Códigos de error y aviso (`TOP-BKT-003`...) y qué hacer con cada uno |
| [docs/desarrollo.md](docs/desarrollo.md) | Módulos del backend y del frontend, tests |
