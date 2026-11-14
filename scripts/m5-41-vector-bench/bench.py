#!/usr/bin/env python3
"""Vector search at 10^4 to 10^6 entries: in the process against pgvector, exact and HNSW (M5-41, ``adr/0026`` F3).

    PGDATABASE=<scratch database> python scripts/m5-41-vector-bench/bench.py --n 100000 --dim 384
    PGDATABASE=<scratch database> python scripts/m5-41-vector-bench/bench.py --corpus c.npy --queries q.npy

The connection comes from the libpq variables (``PGHOST``, ``PGUSER``, ``PGPASSWORD``, ``PGDATABASE``). The database
needs ``vector`` 0.8.0 or later and must be a scratch database: the script creates and drops ``m541_*`` tables in it.

Without ``--corpus`` the vectors are synthetic (``synthetic``): unit vectors with a common direction, clustered on a
low-dimensional subspace, so that pairs are as similar as text embeddings tend to be. Recall on them does not carry over
to real embeddings; ``--corpus``/``--queries`` take ``float32`` arrays of shape (n, dim) from the real model (e5 with
the prefixes ``passage: `` and ``query: ``), normalised here.

Two filters stand in for the hard filters of the search (space, time, access): ``u`` is uniform and independent of the
vector (a filter that does not care about content), ``grp`` is the nearest of 256 sample rows, so a filter on ``grp``
keeps whole regions of the space (the hard case: the query's neighbours mostly fail the filter). Each is asked at 1 %
and 10 % of the rows.

Measured per step, one JSON line each: the in-process search with numpy on one thread (option V2 of
``plans/m5/m5-35-skalierbarkeit.md`` §5.3), the fetch of the filtered vectors per query (V1), pgvector without index
(V3), HNSW on ``vector`` and on ``halfvec`` with ``ef_search`` 40/100/200, iterative scans off/strict/relaxed (V4),
and binary quantisation with re-ranking. Recall is against the exact float32 top k among the rows that pass the filter.
"""

import argparse
import gc
import json
import os
import struct
import sys
import time

os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")

import numpy  # noqa: E402
import psycopg  # noqa: E402

K_MAX = 50
GROUPS = 256
EF_SEARCH = (40, 100, 200)
ITERATIVE = ("off", "strict_order", "relaxed_order")
TABLE = "m541_vec"
HALF_TABLE = "m541_half"
ARRAY_TABLE = "m541_arr"


def emit(step, **values):
    print(json.dumps({"step": step, **values}), flush=True)


def normalise(x):
    return (x / numpy.linalg.norm(x, axis=1, keepdims=True)).astype(numpy.float32)


def synthetic(n, q, dim, seed):
    """Corpus and queries from one generator; queries are fresh draws, not rows of the corpus."""
    rng = numpy.random.default_rng(seed)
    rank = 64
    basis = rng.standard_normal((rank, dim)).astype(numpy.float32) / numpy.sqrt(rank)
    common = rng.standard_normal(dim).astype(numpy.float32)
    common /= numpy.linalg.norm(common)
    centres = rng.standard_normal((max(64, n // 500), rank)).astype(numpy.float32)

    def draw(count):
        out = numpy.empty((count, dim), numpy.float32)
        for start in range(0, count, 50_000):
            m = min(50_000, count - start)
            z = centres[rng.integers(len(centres), size=m)] + 0.7 * rng.standard_normal((m, rank), numpy.float32)
            x = z @ basis + 0.35 * rng.standard_normal((m, dim), numpy.float32) + 2.2 * numpy.sqrt(dim) * common
            out[start : start + m] = normalise(x)
        return out

    return draw(n), draw(q)


def similarity_profile(corpus, queries):
    """Mean cosine of random pairs and of each query's nearest row: how close the space is to text embeddings."""
    rng = numpy.random.default_rng(1)
    a = corpus[rng.integers(len(corpus), size=2000)]
    b = corpus[rng.integers(len(corpus), size=2000)]
    nearest = (queries[:50] @ corpus.T).max(axis=1)
    return {"pair_cos_mean": round(float((a * b).sum(axis=1).mean()), 3), "nn1_cos_mean": round(float(nearest.mean()), 3)}


def filters(corpus, seed):
    rng = numpy.random.default_rng(seed + 7)
    u = rng.integers(0, 1000, size=len(corpus)).astype(numpy.int32)
    anchors = corpus[rng.choice(len(corpus), size=GROUPS, replace=False)]
    grp = numpy.empty(len(corpus), numpy.int32)
    for start in range(0, len(corpus), 100_000):
        grp[start : start + 100_000] = (corpus[start : start + 100_000] @ anchors.T).argmax(axis=1)
    counts = numpy.bincount(grp, minlength=GROUPS)
    order = rng.permutation(GROUPS)

    def groups_for(share):
        chosen, total = [], 0
        for g in order:
            if total >= share * len(corpus):
                break
            if counts[g]:
                chosen.append(int(g))
                total += counts[g]
        return chosen

    cases = {"none": (None, None, numpy.ones(len(corpus), bool))}
    for share, label in ((0.01, "1"), (0.10, "10")):
        cases[f"u{label}"] = ("u < %s", int(share * 1000), u < int(share * 1000))
        chosen = groups_for(share)
        cases[f"grp{label}"] = ("grp = ANY(%s)", chosen, numpy.isin(grp, chosen))
    return u, grp, cases


def exact_top(corpus, queries, mask, k):
    rows = numpy.flatnonzero(mask)
    sub = corpus[rows]
    scores = queries @ sub.T
    k = min(k, len(rows))
    part = numpy.argpartition(-scores, k - 1, axis=1)[:, :k]
    order = numpy.take_along_axis(scores, part, axis=1).argsort(axis=1)[:, ::-1]
    return rows[numpy.take_along_axis(part, order, axis=1)]


def pct(values, p):
    return round(float(numpy.percentile(values, p)) * 1000, 2)


def in_process(corpus, queries, cases, repeat):
    """V2: matrix in the process, mask, one matrix-vector product, partial sort; one thread."""
    for name, (_, _, mask) in cases.items():
        times = []
        for q in queries[:repeat]:
            t0 = time.perf_counter()
            scores = corpus @ q if name == "none" else corpus[numpy.flatnonzero(mask)] @ q
            top = numpy.argpartition(-scores, K_MAX)[:K_MAX]
            top[numpy.argsort(-scores[top])]
            times.append(time.perf_counter() - t0)
        emit("numpy", filter=name, rows=int(mask.sum()), p50_ms=pct(times, 50), p95_ms=pct(times, 95))


def copy_binary(conn, corpus, u, grp):
    """Binary COPY: int4 id, int4 u, int4 grp, vector as int2 dim, int2 0, float4 big-endian."""
    n, dim = corpus.shape
    row = numpy.dtype(
        [
            ("nf", ">i2"), ("l1", ">i4"), ("id", ">i4"), ("l2", ">i4"), ("u", ">i4"), ("l3", ">i4"), ("grp", ">i4"),
            ("l4", ">i4"), ("dim", ">i2"), ("unused", ">i2"), ("v", ">f4", (dim,)),
        ]
    )
    with conn.cursor().copy(f"COPY {TABLE} (id, u, grp, emb) FROM STDIN (FORMAT binary)") as copy:
        copy.write(b"PGCOPY\n\xff\r\n\x00" + struct.pack(">ii", 0, 0))
        for start in range(0, n, 20_000):
            m = min(20_000, n - start)
            block = numpy.empty(m, row)
            block["nf"], block["l1"], block["l2"], block["l3"] = 4, 4, 4, 4
            block["l4"], block["dim"], block["unused"] = 4 + 4 * dim, dim, 0
            block["id"] = numpy.arange(start, start + m)
            block["u"], block["grp"] = u[start : start + m], grp[start : start + m]
            block["v"] = corpus[start : start + m]
            copy.write(block.tobytes())
        copy.write(struct.pack(">h", -1))


def size(conn, relation):
    return conn.execute("SELECT pg_total_relation_size(%s::regclass)", (relation,)).fetchone()[0]


def literal(q):
    return "[" + ",".join(f"{x:.6f}" for x in q) + "]"


def run_queries(conn, sql, queries, case_param, k, truth, settings, label, **extra):
    with conn.transaction():
        for key, value in settings.items():
            conn.execute(f"SET LOCAL {key} = {value}")
        params = ([case_param] if case_param is not None else []) + [literal(queries[0]), k]
        at = len(params) - 2
        plan = conn.execute("EXPLAIN (FORMAT JSON) " + sql, params).fetchone()[0][0]["Plan"]
        node = plan
        while node.get("Plans") and node["Node Type"] in ("Limit", "Sort", "Gather Merge", "Subquery Scan", "Gather"):
            node = node["Plans"][0]
        times, recalls, counts = [], [], []
        conn.execute(sql, params).fetchall()
        for i, q in enumerate(queries):
            params[at] = literal(q)
            t0 = time.perf_counter()
            ids = [r[0] for r in conn.execute(sql, params).fetchall()]
            times.append(time.perf_counter() - t0)
            want = truth[i][:k]
            recalls.append(len(set(ids) & set(want.tolist())) / len(want))
            counts.append(len(ids))
    emit(
        label, k=k, **extra, **{k_: v for k_, v in settings.items() if k_.startswith("hnsw")},
        plan=node["Node Type"] + (":" + node.get("Index Name", "") if "Index Name" in node else ""),
        recall=round(float(numpy.mean(recalls)), 4), returned_mean=round(float(numpy.mean(counts)), 1),
        p50_ms=pct(times, 50), p95_ms=pct(times, 95), queries=len(queries),
    )


def knn_sql(table, dim, cast, where):
    expr = f"emb::{cast}({dim})" if cast else "emb"
    qtype = f"{cast or 'vector'}({dim})"
    cond = f"WHERE {where} " if where else ""
    return f"SELECT id FROM {table} {cond}ORDER BY {expr} <=> %s::{qtype} LIMIT %s"


def hnsw_sweep(conn, table, dim, queries, cases, truths, label, cast=None):
    for name, (where, param, _) in cases.items():
        sql = knn_sql(table, dim, cast, where)
        for k in (10, K_MAX):
            for ef in EF_SEARCH:
                for it in ITERATIVE if name != "none" or k == K_MAX else ("off",):
                    run_queries(
                        conn, sql, queries, param, k, truths[name],
                        {"hnsw.ef_search": ef, "hnsw.iterative_scan": it, "enable_seqscan": "off"},
                        label, filter=name,
                    )
    conn.execute(f"CREATE INDEX {table}_u ON {table} (u)")
    conn.execute(f"CREATE INDEX {table}_grp ON {table} (grp)")
    conn.execute(f"ANALYZE {table}")
    for name, (where, param, _) in cases.items():
        for k in (10, K_MAX):
            run_queries(
                conn, knn_sql(table, dim, cast, where), queries, param, k, truths[name],
                {"hnsw.ef_search": 100, "hnsw.iterative_scan": "relaxed_order"},
                label + "_planner", filter=name,
            )
    conn.execute(f"DROP INDEX {table}_u, {table}_grp")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, default=10_000)
    parser.add_argument("--dim", type=int, default=384)
    parser.add_argument("--queries-n", type=int, default=200)
    parser.add_argument("--corpus")
    parser.add_argument("--queries")
    parser.add_argument("--seed", type=int, default=41)
    parser.add_argument("--workers", type=int, default=3, help="max_parallel_maintenance_workers (plus the leader)")
    parser.add_argument("--build-mem", default="5GB", help="maintenance_work_mem for the index builds")
    parser.add_argument("--skip-vector-index", action="store_true", help="build HNSW on halfvec only")
    args = parser.parse_args()

    if args.corpus:
        corpus, queries = normalise(numpy.load(args.corpus)), normalise(numpy.load(args.queries))
        source = "file"
    else:
        corpus, queries = synthetic(args.n, args.queries_n, args.dim, args.seed)
        source = "synthetic"
    n, dim = corpus.shape
    emit("data", source=source, n=n, dim=dim, queries=len(queries), **similarity_profile(corpus, queries))

    u, grp, cases = filters(corpus, args.seed)
    truths = {name: exact_top(corpus, queries, mask, K_MAX) for name, (_, _, mask) in cases.items()}
    in_process(corpus, queries, cases, repeat=min(len(queries), 50))
    emit("numpy_memory", float32_mb=round(corpus.nbytes / 2**20, 1), float16_mb=round(corpus.nbytes / 2**21, 1))

    with psycopg.connect(autocommit=True) as conn:
        version = conn.execute("SELECT extversion FROM pg_extension WHERE extname = 'vector'").fetchone()
        if not version:
            sys.exit("the database has no extension vector")
        for t in (TABLE, HALF_TABLE, ARRAY_TABLE):
            conn.execute(f"DROP TABLE IF EXISTS {t}")
        conn.execute(f"CREATE TABLE {TABLE} (id int4 PRIMARY KEY, u int4, grp int4, emb vector({dim}))")
        t0 = time.perf_counter()
        copy_binary(conn, corpus, u, grp)
        emit("load_vector", seconds=round(time.perf_counter() - t0, 1), pgvector=version[0])
        del corpus
        gc.collect()
        conn.execute(f"CREATE TABLE {HALF_TABLE} AS SELECT id, u, grp, emb::halfvec({dim}) AS emb FROM {TABLE}")
        conn.execute(f"ALTER TABLE {HALF_TABLE} ADD PRIMARY KEY (id)")
        conn.execute(f"ANALYZE {TABLE}")
        conn.execute(f"ANALYZE {HALF_TABLE}")
        emit("table_size", vector_mb=round(size(conn, TABLE) / 2**20, 1), halfvec_mb=round(size(conn, HALF_TABLE) / 2**20, 1))

        t0 = time.perf_counter()
        buf = bytearray()
        with conn.cursor().copy(f"COPY (SELECT emb FROM {HALF_TABLE} ORDER BY id) TO STDOUT (FORMAT binary)") as copy:
            for chunk in copy:
                buf += chunk
        emit("startup_load_v2", seconds=round(time.perf_counter() - t0, 2), mb=round(len(buf) / 2**20, 1))
        del buf

        if n <= 100_000:
            conn.execute(f"CREATE TABLE {ARRAY_TABLE} AS SELECT id, u, grp, emb::real[] AS emb FROM {TABLE}")
            for name in ("none", "u10"):
                where, param, _ = cases[name]
                sql = f"SELECT id, emb FROM {ARRAY_TABLE}" + (f" WHERE {where}" if where else "")
                times = []
                for _ in range(5):
                    t0 = time.perf_counter()
                    rows = conn.execute(sql, [param] if param is not None else []).fetchall()
                    numpy.array([r[1] for r in rows], numpy.float32)
                    times.append(time.perf_counter() - t0)
                emit("fetch_per_query_v1", filter=name, rows=len(rows), p50_ms=pct(times, 50))
            conn.execute(f"DROP TABLE {ARRAY_TABLE}")

        exact_q = queries[: 20 if n >= 1_000_000 else 50]
        exact_truth = {name: t[: len(exact_q)] for name, t in truths.items()}
        for workers in (0, 2):
            for table, cast, label in ((TABLE, None, "exact_vector"), (HALF_TABLE, "halfvec", "exact_halfvec")):
                for name in ("none", "u10", "grp1"):
                    where, param, _ = cases[name]
                    run_queries(
                        conn, knn_sql(table, dim, cast, where), exact_q, param, 10, exact_truth[name],
                        {"max_parallel_workers_per_gather": workers, "enable_indexscan": "off"},
                        label, filter=name, workers=workers,
                    )

        conn.execute(f"SET maintenance_work_mem = '{args.build_mem}'")
        conn.execute(f"SET max_parallel_maintenance_workers = {args.workers}")
        builds = [(HALF_TABLE, "halfvec", "hnsw_halfvec")]
        if not args.skip_vector_index:
            builds.insert(0, (TABLE, None, "hnsw_vector"))
        for table, cast, label in builds:
            ops = f"{cast or 'vector'}_cosine_ops"
            t0 = time.perf_counter()
            conn.execute(f"CREATE INDEX {table}_hnsw ON {table} USING hnsw (emb {ops})")
            emit(
                f"{label}_build", seconds=round(time.perf_counter() - t0, 1), workers=args.workers + 1,
                index_mb=round(conn.execute(f"SELECT pg_relation_size('{table}_hnsw')").fetchone()[0] / 2**20, 1),
            )
            hnsw_sweep(conn, table, dim, queries, cases, truths, label, cast=cast)
            if label == "hnsw_halfvec":
                throughput(queries, dim)
            conn.execute(f"DROP INDEX {table}_hnsw")

        binary_quantisation(conn, dim, queries, truths["none"])
        for t in (TABLE, HALF_TABLE):
            conn.execute(f"DROP TABLE {t}")


def throughput(queries, dim):
    """Queries per second against the halfvec index with 1 and 4 clients (ef_search 100, no filter, k 10)."""
    import threading

    sql = knn_sql(HALF_TABLE, dim, "halfvec", None)
    for clients in (1, 4):
        done = []

        def worker(offset, done=done):
            with psycopg.connect(autocommit=True) as c:
                c.execute("SET hnsw.ef_search = 100")
                for q in numpy.roll(queries, offset, axis=0):
                    c.execute(sql, [literal(q), 10]).fetchall()
                    done.append(1)

        threads = [threading.Thread(target=worker, args=(i * 17,)) for i in range(clients)]
        t0 = time.perf_counter()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        emit("hnsw_halfvec_qps", clients=clients, qps=round(len(done) / (time.perf_counter() - t0), 1))


def binary_quantisation(conn, dim, queries, truth):
    """HNSW on binary_quantize(emb) with Hamming distance, re-ranked by the full vector (pgvector README)."""
    t0 = time.perf_counter()
    conn.execute(
        f"CREATE INDEX {TABLE}_bq ON {TABLE} USING hnsw ((binary_quantize(emb)::bit({dim})) bit_hamming_ops)"
    )
    emit(
        "bq_build", seconds=round(time.perf_counter() - t0, 1),
        index_mb=round(conn.execute(f"SELECT pg_relation_size('{TABLE}_bq')").fetchone()[0] / 2**20, 1),
    )
    for depth in (40, 200):
        sql = (
            f"SELECT id FROM (SELECT id, emb FROM {TABLE} ORDER BY binary_quantize(emb)::bit({dim}) <~> "
            f"binary_quantize(%s::vector({dim})) LIMIT {depth}) s ORDER BY emb <=> %s::vector({dim}) LIMIT 10"
        )
        times, recalls = [], []
        with conn.transaction():
            conn.execute(f"SET LOCAL hnsw.ef_search = {max(depth, 40)}")
            for i, q in enumerate(queries):
                lit = literal(q)
                t0 = time.perf_counter()
                ids = [r[0] for r in conn.execute(sql, [lit, lit]).fetchall()]
                times.append(time.perf_counter() - t0)
                recalls.append(len(set(ids) & set(truth[i][:10].tolist())) / 10)
        emit("bq_rerank", depth=depth, recall=round(float(numpy.mean(recalls)), 4), p50_ms=pct(times, 50), p95_ms=pct(times, 95))
    conn.execute(f"DROP INDEX {TABLE}_bq")


if __name__ == "__main__":
    main()
