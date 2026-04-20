import psycopg2
import sys

DB_URL = 'postgresql://user:password@localhost:5432/market_db'

def main():
    try:
        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()

        print('--- Query 1: Count ---')
        cur.execute('SELECT count(*) FROM documents;')
        print(cur.fetchone()[0])

        print('\n--- Query 2: Recent 3 Documents ---')
        cur.execute('SELECT title, length(raw_text) as text_len, metadata_json FROM documents ORDER BY processed_at DESC LIMIT 3;')
        for row in cur.fetchall():
            print(row)

        print('\n--- Query 3: Latest Document Text ---')
        cur.execute('SELECT raw_text FROM documents ORDER BY processed_at DESC LIMIT 1;')
        res = cur.fetchone()
        if res:
            print(res[0])
        else:
            print('No documents found.')

        cur.close()
        conn.close()
    except Exception as e:
        print(f'Error: {e}')

if __name__ == '__main__':
    main()
