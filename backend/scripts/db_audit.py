#!/usr/bin/env python3
import os
import asyncio
import json
from dotenv import load_dotenv
import asyncpg

load_dotenv('.env.local')

async def run():
    db_url = os.environ.get('DATABASE_URL')
    if not db_url:
        print(json.dumps({'error':'DATABASE_URL not set in .env.local'}))
        return
    conn = await asyncpg.connect(db_url)
    out = {}
    try:
        # Tables of interest
        tables = ['papers','user_profiles','academic_programme_submissions','academic_programme_aliases','comments','solutions','reports']
        # Index listing
        idx_query = """
        SELECT tablename, indexname, indexdef
        FROM pg_indexes
        WHERE schemaname = 'public' AND tablename = ANY($1::text[])
        ORDER BY tablename, indexname;
        """
        idx_rows = await conn.fetch(idx_query, tables)
        out['indexes'] = [dict(r) for r in idx_rows]

        # Table stats: row counts and sizes
        stats = {}
        for t in tables:
            row = await conn.fetchrow('SELECT COUNT(*) AS count FROM ' + t + ';')
            size = await conn.fetchrow("SELECT pg_total_relation_size($1) AS total_size, pg_relation_size($1) AS rel_size", t)
            stats[t] = {'row_count': row['count'], 'total_size': size['total_size'], 'table_size': size['rel_size']}
        out['table_stats'] = stats

        # Index sizes via pg_indexes
        idx_sizes = []
        for r in idx_rows:
            try:
                q = "SELECT pg_relation_size($1::regclass) AS size";
                size_row = await conn.fetchrow(q, r['indexname'])
                idx_sizes.append({'tablename': r['tablename'], 'indexname': r['indexname'], 'size': size_row['size']})
            except Exception:
                idx_sizes.append({'tablename': r['tablename'], 'indexname': r['indexname'], 'size': None})
        out['index_sizes'] = idx_sizes

        # Sample values for filtering
        sample = {}
        cols = ['institution_id','campus_id','college_id','school_id','programme_id','user_id']
        for col in cols:
            try:
                row = await conn.fetchrow(f"SELECT {col} FROM papers WHERE {col} IS NOT NULL LIMIT 1")
                sample[col] = row[col] if row else None
            except Exception:
                sample[col] = None
        out['sample_values'] = sample

        # Representative queries - we'll build a few safely
        explain_results = {}

        # 1. GET /api/v1/entities/papers/all?sort=-download_count&limit=50&skip=0
        q1 = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM papers ORDER BY download_count DESC NULLS LAST OFFSET 0 LIMIT 50;"
        r1 = await conn.fetch(q1)
        explain_results['papers_all_sort_downloads'] = r1[0][0]

        # 2. public papers ordered by download_count
        q2 = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM papers WHERE (is_hidden IS NOT TRUE AND verification_status = 'verified') ORDER BY download_count DESC NULLS LAST LIMIT 50;"
        r2 = await conn.fetch(q2)
        explain_results['public_papers_downloads'] = r2[0][0]

        # 3. recent papers ordered by created_at
        q3 = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM papers WHERE (is_hidden IS NOT TRUE AND verification_status = 'verified') ORDER BY created_at DESC NULLS LAST LIMIT 50;"
        r3 = await conn.fetch(q3)
        explain_results['public_papers_created'] = r3[0][0]

        # 4. papers filtered by institution_id (use sample if available)
        inst = sample.get('institution_id')
        if inst:
            q4 = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM papers WHERE institution_id = $1 ORDER BY id DESC LIMIT 50;"
            r4 = await conn.fetch(q4, inst)
            explain_results['papers_by_institution'] = r4[0][0]
        else:
            explain_results['papers_by_institution'] = None

        # 5. papers filtered by institution + campus
        campus = sample.get('campus_id')
        if inst and campus:
            q5 = f"EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM papers WHERE institution_id = $1 AND campus_id = $2 ORDER BY id DESC LIMIT 50;"
            r5 = await conn.fetch(q5, inst, campus)
            explain_results['papers_by_institution_campus'] = r5[0][0]
        else:
            explain_results['papers_by_institution_campus'] = None

        # 6. papers filtered by programme_id (sample)
        prog = sample.get('programme_id')
        if prog:
            q6 = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM papers WHERE programme_id = $1 ORDER BY download_count DESC LIMIT 50;"
            r6 = await conn.fetch(q6, prog)
            explain_results['papers_by_programme'] = r6[0][0]
        else:
            explain_results['papers_by_programme'] = None

        # 7. papers filtered by verification_status / is_hidden
        q7 = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM papers WHERE verification_status = 'verified' AND (is_hidden IS NOT TRUE) ORDER BY id DESC LIMIT 50;"
        r7 = await conn.fetch(q7)
        explain_results['papers_verified_hidden'] = r7[0][0]

        # 8. user_profiles lookup by user_id (use sample user_id if available)
        uid = sample.get('user_id')
        if uid:
            q8 = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM user_profiles WHERE user_id = $1;"
            r8 = await conn.fetch(q8, uid)
            explain_results['user_profiles_by_user_id'] = r8[0][0]
        else:
            explain_results['user_profiles_by_user_id'] = None

        # 9. academic_programme_submissions filtered by institution_id + school_id
        school = sample.get('school_id')
        if inst and school:
            q9 = "EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) SELECT * FROM academic_programme_submissions WHERE institution_id = $1 AND school_id = $2;"
            r9 = await conn.fetch(q9, inst, school)
            explain_results['programme_submissions_by_context'] = r9[0][0]
        else:
            explain_results['programme_submissions_by_context'] = None

        out['explain'] = explain_results

        # pg_stat_user_indexes basic usage stats
        stats_q = "SELECT relname AS table_name, indexrelname AS index_name, idx_scan, idx_tup_read, idx_tup_fetch FROM pg_stat_user_indexes WHERE relname = ANY($1::text[]);"
        stats_rows = await conn.fetch(stats_q, tables)
        out['pg_stat_user_indexes'] = [dict(r) for r in stats_rows]

        print(json.dumps(out, default=str))
    finally:
        await conn.close()

if __name__ == '__main__':
    asyncio.run(run())
