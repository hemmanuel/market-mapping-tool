import psycopg2

DB_URL = 'postgresql://user:password@localhost:5432/market_db'

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    query = '''
    SELECT 
        d.id as document_id, 
        ds.name as source_name,
        s.name as site_name, 
        t.auth_id as user_id
    FROM documents d
    JOIN data_sources ds ON d.data_source_id = ds.id
    JOIN sites s ON ds.site_id = s.id
    JOIN tenants t ON s.tenant_id = t.id
    LIMIT 3;
    '''
    cur.execute(query)
    rows = cur.fetchall()
    print('document_id | source_name | site_name | user_id')
    print('-' * 60)
    for row in rows:
        print(f'{row[0]} | {row[1]} | {row[2]} | {row[3]}')
    
    cur.close()
    conn.close()
except Exception as e:
    print(f'Error: {e}')
