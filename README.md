# PRISM — Permitting Risk Index & Spatial Model

A national-scale H3-hex web map of environmental and permitting friction across the United States. PRISM scores each ~460m² hex by the layered presence of authoritative environmental, historic, and regulatory data (USFWS Critical Habitat, FEMA Flood Hazards, NWI Wetlands, NRHP, BLM/USFS/NPS, EPA programs, Tribal lands, and more — 205 layers from the APPEIT catalog) so broadband deployers, state broadband offices, and permitting professionals can see where infrastructure projects will face high, medium, or low environmental review burden before a single route is designed.

PRISM ships as a standalone Next.js + Mapbox GL app at `prism.kucimaps.com`, and exports a Mapbox layer (`@prism/map-layer`) for embedding inside HexRoute.

## Status

🚧 **Pilot phase** — Vermont + Nevada only. National expansion follows pilot validation.

## Stack

- **Frontend**: Next.js 16 (App Router), React 19, TypeScript strict, Tailwind v4, shadcn/ui (dark-first), Zustand, Mapbox GL JS 3.18
- **Backend**: Supabase (PostgreSQL + PostGIS + h3 extension), Vercel
- **Data pipeline**: Local Python (conda `claude` env) using H3, GeoPandas, Shapely, lifted ArcGIS query logic from PEIT Map Creator
- **Compute (later)**: Modal.com for the Phase 6 paid analysis feature

## Layout

```
prism/
├── app/                  # Next.js App Router (map page, /api/tiles, /api/hex/[h3_index])
├── components/           # map/ filters/ panels/ ui/
├── lib/                  # supabase, store (zustand), h3, tiles, file-parsers
├── modal/                # Python pipeline (ingest, indexing, scoring)
├── packages/
│   └── prism-map-layer/  # exportable Mapbox layer for HexRoute
├── supabase/
│   └── migrations/       # 001_extensions.sql … 007_mvt_rpc.sql
└── PRISM_PROJECT_PROMPT.md  # original project brief
```

## Quick start

```bash
# Clone
git clone https://github.com/lukaskucinski/prism.git
cd prism

# Frontend
pnpm install
cp .env.example .env.local   # add Supabase URL, anon key, Mapbox token
pnpm dev

# Python pipeline (conda 'claude' env)
conda activate claude
pip install -e modal/
python -m prism.boundaries.load_tiger
python -m prism.ingest --states VT,NV
python -m prism.index --states VT,NV
python -m prism.score
```

## Reference

- Full spec: [PRISM_PROJECT_PROMPT.md](./PRISM_PROJECT_PROMPT.md)
- Implementation plan: maintained in `~/.claude/plans/`

## License

Proprietary — Kucinski.
