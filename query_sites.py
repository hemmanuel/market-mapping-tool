import psycopg2

db_url = 'postgresql://user:password@localhost:5432/market_db'
query = '''
SELECT s.id, s.name, s.created_at
FROM sites s
JOIN tenants t ON s.tenant_id = t.id
WHERE t.auth_id = 'user_3By72RKijkR6dHeQDDrxaznfJxE'
ORDER BY s.created_at DESC;
'''

try:
    conn = psycopg2.connect(db_url)
    cur = conn.cursor()
    cur.execute(query)
    rows = cur.fetchall()
    if not rows:
        print('No sites found.')
    for row in rows:
        print(f'ID: {row[0]} | Name: {row[1]} | Created At: {row[2]}')
    cur.close()
    conn.close()
except Exception as e:
    print(f'Error: {e}')
