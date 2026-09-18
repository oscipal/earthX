import { parseAoiFile } from '../aoiFile';
import { bufferPointToPolygon, polygonBbox } from '../geoUtils';
import { PRODUCTS } from '../products';
import { useAppStore } from '../store';
import SearchBox from './SearchBox';
import Toolbar from './Toolbar';

function AoiExtras() {
  const setAoi = useAppStore((s) => s.setAoi);
  const flyTo = useAppStore((s) => s.flyTo);
  const applyLastAoi = useAppStore((s) => s.useLastAoi);
  const lastAoi = useAppStore((s) => s.lastAoi);
  const config = useAppStore((s) => s.config);
  const setError = useAppStore((s) => s.setError);

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    try {
      let geom = parseAoiFile(file.name, await file.text());
      if (!geom) {
        setError(`Could not read an AOI geometry from "${file.name}".`);
        return;
      }
      if (geom.type === 'Point') {
        const [lon, lat] = geom.coordinates;
        geom = bufferPointToPolygon(lon, lat, config?.point_buffer_deg ?? 0.05);
      }
      setAoi(geom);
      const bb = polygonBbox(geom);
      if (bb) flyTo(bb);
    } catch (err) {
      setError(`Failed to load AOI file: ${(err as Error).message}`);
    }
  };

  return (
    <div className="aoi-extras">
      <label className="tool-btn ghost" title="Upload a KML or GeoJSON to use as the AOI">
        <input
          type="file"
          accept=".kml,.json,.geojson,application/json,application/vnd.google-earth.kml+xml"
          onChange={onFile}
          hidden
        />
        <span>⤒ Upload KML/JSON</span>
      </label>
      <button
        type="button"
        className="tool-btn ghost"
        disabled={!lastAoi}
        title="Reuse the previous area of interest"
        onClick={() => applyLastAoi()}
      >
        <span>↺ Last AOI</span>
      </button>
    </div>
  );
}

function ProductSelector() {
  const product = useAppStore((s) => s.product);
  const setProduct = useAppStore((s) => s.setProduct);
  return (
    <div className="level-select" role="group" aria-label="Product">
      {PRODUCTS.map((p) => (
        <button
          key={p.id}
          type="button"
          className={`level-btn${product === p.id ? ' active' : ''}`}
          title={p.hint}
          aria-pressed={product === p.id}
          onClick={() => setProduct(p.id)}
        >
          {p.label}
        </button>
      ))}
    </div>
  );
}

function CoverageToggle() {
  const showCoverage = useAppStore((s) => s.showCoverage);
  const coverageLoading = useAppStore((s) => s.coverageLoading);
  const toggleCoverage = useAppStore((s) => s.toggleCoverage);
  return (
    <button
      type="button"
      className={`tool-btn ghost coverage-toggle${showCoverage ? ' active' : ''}`}
      title="Show where BIOMASS has data (global scene footprints for this product)"
      aria-pressed={showCoverage}
      onClick={() => toggleCoverage()}
    >
      {coverageLoading && <span className="spinner" aria-hidden="true" />}
      <span>▦ {showCoverage ? 'Hide' : 'Show'} BIOMASS coverage</span>
    </button>
  );
}

export default function ControlPanel() {
  const aoi = useAppStore((s) => s.aoi);
  const dateFrom = useAppStore((s) => s.dateFrom);
  const dateTo = useAppStore((s) => s.dateTo);
  const setDateFrom = useAppStore((s) => s.setDateFrom);
  const setDateTo = useAppStore((s) => s.setDateTo);
  const searching = useAppStore((s) => s.searching);
  const runSearch = useAppStore((s) => s.runSearch);
  const count = useAppStore((s) => s.items.length);

  return (
    <div className="panel control-panel">
      <div className="brand">
        <span className="brand-mark" />
        <div>
          <h1>BIOMASS VIEWER</h1>
          <p>ESA BIOMASS · P-band SAR · AGB</p>
        </div>
      </div>

      <label className="field-label">Area of interest</label>
      <SearchBox />
      <Toolbar />
      <AoiExtras />

      <label className="field-label">Product</label>
      <ProductSelector />
      <CoverageToggle />

      <label className="field-label">Acquisition date</label>
      <div className="date-row">
        <input
          type="date"
          value={dateFrom}
          onChange={(e) => setDateFrom(e.target.value)}
          aria-label="From date"
        />
        <span>→</span>
        <input
          type="date"
          value={dateTo}
          onChange={(e) => setDateTo(e.target.value)}
          aria-label="To date"
        />
      </div>

      <button
        type="button"
        className="primary-btn"
        disabled={!aoi || searching}
        onClick={() => runSearch()}
      >
        {searching ? 'Searching…' : 'Search scenes'}
      </button>

      {count > 0 && <p className="result-count">{count} scene(s) found</p>}
      {!aoi && <p className="hint-text">Pick a tool or search a place to define an AOI.</p>}
    </div>
  );
}
