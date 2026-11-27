\set ON_ERROR_STOP on
-- PostGIS first, with its own helper: it also updates postgis_topology and postgis_raster.
SELECT 'SELECT postgis_extensions_upgrade()' WHERE EXISTS (SELECT 1 FROM pg_extension WHERE extname = 'postgis') \gexec
-- The rest; an extension the new image no longer ships (postgis_tiger_geocoder) is left as it is.
SELECT format('ALTER EXTENSION %I UPDATE', extname) FROM pg_extension
WHERE extname IN (SELECT name FROM pg_available_extensions) ORDER BY extname \gexec
-- glibc 2.31 (bullseye) to 2.41 (trixie): text indexes are rebuilt before the new version is recorded.
REINDEX DATABASE;
SELECT format('ALTER DATABASE %I REFRESH COLLATION VERSION', current_database()) \gexec
