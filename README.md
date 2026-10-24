# sp500-momentum-top-n

Estrategia de momentum sobre el S&P 500: cada N meses se compran, con ponderación igual, las N acciones que más
subieron en los últimos N meses. El proyecto la evalúa con datos históricos (backtest), mide cuánto del resultado
depende del mes de arranque y muestra los resultados en una aplicación web local.

Además calcula el **Top actual** (qué acciones lidera hoy el ranking, con sus suplentes, los cambios respecto de la
corrida anterior y el próximo rebalanceo) y un **ranking de momentum de los ETFs de Vanguard** ajustado por riesgo.

> **Aviso:** es una herramienta de análisis, no una recomendación de inversión. El backtest no incluye comisiones
> ni impuestos y tiene sesgos de datos (ver [Limitaciones](docs/como-funciona.md#limitaciones)).

## Qué incluye

| Funcionalidad | Dónde se ve |
|---|---|
| **Backtest** Point-in-Time: comparación de plazos y sensibilidad al mes de arranque, por universo (índice completo, large-cap, mega-cap) y por período | Pestañas *Backtest* y *Plazos y sensibilidad* |
| **Comparación N-0 vs. N-1**: el modelo de siempre frente a una variante *skip-month* que ignora el último mes al rankear, plazo por plazo | Pestaña *N-0 vs N-1* |
| **Top actual**: las N acciones con mejor retorno hoy, cuatro suplentes, qué entra y qué sale, próximo rebalanceo | Pestaña *Top actual* |
| **ETFs de Vanguard**: ranking por retorno ajustado por riesgo, con tendencia y caída máxima | Pestaña *ETFs Vanguard* |
| Reportes por consola y en HTML, con códigos de error estables (`TOP-BKT-003`, ...) | `backend/output/` y [docs/errores.md](docs/errores.md) |

## Requisitos

| Herramienta | Versión | Para qué |
|---|---|---|
| [Python](https://www.python.org/downloads/) | 3.11 o superior | Descarga de datos, cálculos y API |
| [Node.js](https://nodejs.org/) (incluye `npm`) | 20.19 o superior | Interfaz web |
| Conexión a internet | | Descarga de precios y listas del índice |

## Cómo ejecutarlo

El proceso tiene tres pasos: **instalar**, **generar los datos** y **abrir la web**. Los comandos se escriben en
una terminal (en Windows, PowerShell; en macOS y Linux, Terminal). Primero se descarga el proyecto:

```
git clone https://github.com/loc1263/sp500-momentum-top-n.git
cd sp500-momentum-top-n
```

### 1. Instalar las dependencias

```
cd backend
pip install -r requirements.txt
cd ../frontend
npm install
cd ..
```

En macOS y Linux, si `pip` no existe, use `pip3` (y `python3` en lugar de `python` en los pasos siguientes).

### 2. Generar los datos (backend)

```
cd backend
python run_pipeline.py
cd ..
```

Este comando descarga los precios, ejecuta el backtest y el Top actual, calcula el ranking de ETFs y deja todo
guardado en una base SQLite local (`backend/data/`). **La primera vez tarda varios minutos** (descarga más de diez
años de precios); las siguientes ejecuciones son mucho más rápidas porque solo actualizan lo que falta.

Al terminar imprime un resumen con el tiempo de cada paso y los avisos que hayan aparecido.

### 3. Levantar los servidores y abrir la web

Desde la carpeta raíz del proyecto:

| Sistema | Comando |
|---|---|
| Windows (PowerShell) | `.\start.ps1` |
| macOS / Linux | `./start.sh` |

Esto inicia el backend (puerto 8000) y el frontend (puerto 5173). Cuando aparezca el mensaje
`Local: http://localhost:5173/`, abra esa dirección en el navegador:

**http://localhost:5173**

Para detener ambos servidores, presione `Ctrl+C` en la terminal.

<details>
<summary>Levantar los servidores a mano (alternativa a los scripts)</summary>

Se necesitan dos terminales abiertas a la vez.

```
# Terminal 1: backend
cd backend
python server.py

# Terminal 2: frontend
cd frontend
npm run dev
```

</details>

### Actualizar los resultados

Para refrescar los datos (por ejemplo, otro día), vuelva a ejecutar el paso 2 y recargue la página. Los servidores
pueden seguir en marcha.

### Problemas frecuentes

| Síntoma | Solución |
|---|---|
| PowerShell indica que la ejecución de scripts está deshabilitada | Ejecute `powershell -ExecutionPolicy Bypass -File .\start.ps1` o use la alternativa manual |
| La página muestra «No se pudo cargar api/report ni data/report.json» | Falta el paso 2, o el backend no está en marcha. Ejecute `python run_pipeline.py` en `backend/` |
| La pestaña indica «Sin Top actual» o «Sin backtest» | Ejecute `python run_pipeline.py` en `backend/` |
| Error por puerto en uso | Cierre el programa que lo ocupa o cambie el puerto: `.\start.ps1 -BackendPort 9000 -FrontendPort 3000` (Windows) o `BACKEND_PORT=9000 FRONTEND_PORT=3000 ./start.sh` |
| Avisos o errores durante la descarga (`TOP-NET-...`) | Suelen ser problemas de red o límites de Yahoo Finance; vuelva a intentarlo más tarde. Ver [docs/errores.md](docs/errores.md) |

## Comandos útiles

Se ejecutan desde `backend/`:

```
python run_pipeline.py --no-cache        # vuelve a descargar todo
python run_pipeline.py --skip-backtest   # solo Top actual, ETFs y JSON del frontend (rápido)
python top3_backtest.py --sweep          # backtest de todos los plazos y universos
python top3_actual.py                    # Top N de hoy
python top3_etf.py                       # ranking de ETFs de Vanguard
python -m pytest                         # tests del backend (requiere requirements-dev.txt); en frontend/: npm test
```

Todas las opciones están en [docs/uso.md](docs/uso.md) y los parámetros (plazo, cantidad de acciones, capital
inicial, suplentes) en [`backend/config.toml`](backend/config.toml).

## Estructura

```
start.ps1 / start.sh  # levantan backend + frontend (Windows / macOS y Linux)
backend/              # Python: backtest, Top actual, ranking de ETFs, base SQLite y API HTTP
  config.toml         # configuración
  vanguard_etfs.csv   # lista de ETFs de Vanguard (se mantiene a mano)
frontend/             # Aplicación web en Svelte 5 + Vite
docs/                 # documentación detallada
```

## Documentación

| Documento | Contenido |
|---|---|
| [docs/uso.md](docs/uso.md) | Comandos, pipeline completo, modos del backtest, Top actual y ETFs de Vanguard |
| [docs/como-funciona.md](docs/como-funciona.md) | Metodología, universo y capitalización, caché, limitaciones |
| [docs/configuracion.md](docs/configuracion.md) | Todas las claves de `config.toml` |
| [docs/salidas.md](docs/salidas.md) | Reportes HTML, consola, tablas SQLite, logs y limpieza de la base |
| [docs/errores.md](docs/errores.md) | Códigos de error y aviso, y qué hacer con cada uno |
| [docs/desarrollo.md](docs/desarrollo.md) | Módulos del backend y del frontend, tests |

## Fuentes de datos

Los precios se obtienen de Yahoo Finance mediante [`yfinance`](https://github.com/ranaroussi/yfinance); la
composición del índice, del repositorio [`hanshof/sp500_constituents`](https://github.com/hanshof/sp500_constituents)
y de Wikipedia. Su disponibilidad y exactitud no están garantizadas, y su uso queda sujeto a los términos de cada
proveedor. Este proyecto está pensado para uso personal y educativo.

## Licencia

Distribuido bajo la licencia [MIT](LICENSE).
