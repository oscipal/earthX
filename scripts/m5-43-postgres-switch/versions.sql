SELECT 'server', version();
SELECT 'database', datname, coalesce(datcollversion, '-') FROM pg_database ORDER BY datname;
SELECT 'extension', extname, extversion FROM pg_extension ORDER BY extname;
SELECT 'vector offered', coalesce(max(default_version), 'missing') FROM pg_available_extensions WHERE name = 'vector';
SELECT 'size', pg_size_pretty(pg_database_size(current_database()));
SELECT 'setting', name, current_setting(name) FROM (VALUES ('shared_buffers'), ('work_mem')) AS s (name);
