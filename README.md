# STEM Link Satellite MCP (server)

Field-level evidence for AgriVibe, served over MCP with [FastMCP](https://gofastmcp.com):

| Kind | Name | What it gives |
|---|---|---|
| tool | `list_fields` | The fields this server knows: ID, name, crop |
| tool | `search_area` | Finds a square near a named place whose Copernicus land cover matches the crop |
| tool | `get_satellite_analysis` | Sentinel-2 NDVI change, uniformity and data quality |
| tool | `get_weather_context` | Last 7 days of rain and humidity, next 48 hours of rain |
| resource | `fields://registry` | The field registry as JSON |
| resource template | `fields://{field_id}` | One field as JSON |
| prompt | `field_health_brief` | Instructions for a short field brief |

The numbers are measurements. They never diagnose a cause.

## How the code is laid out

```
src/fieldsat/
├── domain/        the engine: contracts, fields, NDVI and rain rules. No MCP in here.
├── providers/     where evidence comes from
│   ├── base.py        the two Protocols every provider implements
│   ├── copernicus.py  live Sentinel-2 Statistical API
│   ├── open_meteo.py  live Open-Meteo forecast API
│   ├── http_retry.py  bounded retries for both
│   └── fixtures.py    fixed numbers for tests and --demo
├── tools/         the MCP tools, one module per area
├── resources.py   MCP resources
├── prompts.py     MCP prompts
├── server.py      create_server(): one FastMCP object with everything registered
├── runtime.py     live server or demo server
├── cli.py         the fieldsat command: data source and transport
└── asgi.py        an ASGI app for uvicorn or a hosting platform
```

Read it from the outside in: `cli.py` → `runtime.py` → `server.py` → `tools/`. The MCP
layer is thin. Everything below `tools/` would work the same without MCP.

The providers are passed in rather than created inside the tools. That is what lets the
same server run on live data, on demo data, and in tests.

## Run

```bash
uv sync
uv run fieldsat --demo                              # stdio
uv run fieldsat --demo --transport http --port 8000 # http://127.0.0.1:8000/mcp
cp .env.example .env   # then add your Copernicus client ID and secret
uv run --env-file .env fieldsat --transport http    # live
```

With stdio, stdout is the protocol channel. Log to stderr (`logging` does by default).
The MCP Python SDK diverts `print()` to stderr once the server is running, but output
printed before that, or by a child process, lands in the protocol stream, and many
clients drop a server that writes non-JSON to stdout.

## Fields: built in, from a file, or searched

**Registered fields.** By default both modes serve the four built-in fields. To serve your own,
write a GeoJSON FeatureCollection like [`fields.example.geojson`](fields.example.geojson) and
pass it with `--fields my-fields.geojson` or `FIELDSAT_FIELDS_FILE=my-fields.geojson`. Each
feature is a Polygon with `id`, `name`, `crop` (`paddy` or `tea`) and an optional `time_zone`
(an IANA name; default `auto`, which takes the zone from the field's location).

**Searched areas.** `search_area(place_name, crop, area_size_m=1000, country_code="LK")`
finds an area without registering it:

1. Open-Meteo's geocoder turns the place name into coordinates. Copernicus has no place-name
   search.
2. The server checks the square centred on the place and the eight squares around it on the
   [Copernicus Global Land Cover Map at 10 m](https://documentation.dataspace.copernicus.eu/APIs/SentinelHub/Data/clms/land-cover-and-land-use-mapping/global-dynamic-land-cover/lcm_global_10m_yearly_v1.html)
   (CLMS LCM10, 2020), using the same Statistical API and credentials as Sentinel-2.
3. It returns the square with the most matching land cover, which must be at least 40%.
   Paddy matches cropland or herbaceous wetland. Tea matches tree cover, shrubland or
   cropland, because the map has no plantation class.

The result's `field_id`, for example `AREA_PADDY_8.04652_80.90251_1000M`, encodes the crop,
centre and size. `get_satellite_analysis` and `get_weather_context` accept it like a
registered ID, and nothing is stored on the server, so it also works with stateless HTTP
hosting. The land-cover map shows where cropland is, not which crop is grown.

## Demo mode

`--demo` (or `STEMLINK_MCP_DEMO=1`) serves fixed numbers for the four real zones and adds
four verification fields that misbehave on purpose:

| Field | Behaviour |
|---|---|
| `SL-PADDY-POOR` | Succeeds, but the data quality is poor |
| `SL-PADDY-SAT-FAIL` | Satellite tool fails with a 503; weather still works |
| `SL-PADDY-WEATHER-FAIL` | Weather tool fails with a 503; satellite still works |
| `SL-PADDY-SLOW` | Satellite tool takes 20 seconds |

With `--fields`, demo mode serves your fields with canonical numbers, plus these four.
`search_area` in demo mode knows Minneriya, Ampara and Nuwara Eliya. It also knows Colombo,
which is mostly built-up, so a paddy search there shows `NO_MATCHING_LAND_COVER`.

## Live data

The live server refuses to start without `COPERNICUS_CLIENT_ID` and
`COPERNICUS_CLIENT_SECRET`. Open-Meteo needs no key. Confirm you are allowed to process
each registered field boundary before you use live data.

Each `search_area` call makes nine small land-cover requests to Copernicus, which count
against your account's processing-unit quota.

## Hosting

`app.py` exports the live ASGI app for platforms that look for it (Vercel, for example).
Locally: `uv run --env-file .env uvicorn fieldsat.asgi:app --port 8000`.

## Checks

```bash
uv run ruff check .
uv run mypy
uv run pytest
uv run python scripts/smoke_mcp.py
```

Restructured from the `stemlink-satellite-mcp` repository (MCP Python SDK 1.x) for this
lesson. The domain and provider code is unchanged apart from module paths; the MCP layer
moved to FastMCP 4, and the server gained `list_fields`, a resource, a prompt, a demo mode
and a transport flag.
