# EarthX frontend

React + TypeScript + Vite + MapLibre viewer for the EarthX platform. It talks
only to `earthx`'s own STAC API under `/stac` — never to the BIOMASS
prototype's `/api/…` routes (see `docs/plans/m2-format-und-viewer.md`).

## Development

```sh
npm install
npm run dev
```

The dev server proxies `/stac` to `http://localhost:8000` by default;
override the target with `VITE_API_PROXY`.

## Checks

```sh
npm run lint          # oxlint
npx tsc -b --pretty false   # type check
npm test               # vitest — pure logic only, no DOM
```
