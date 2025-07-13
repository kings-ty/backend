import psycopg2
import os

# Google Cloud SQL instance information

DB_HOST = ""  # Google Cloud Console "public IP address"
DB_PORT = "5432"            
DB_NAME = "postgres"       
DB_USER = "postgres"        
DB_PASSWORD = "" 

try:

    conn = psycopg2.connect(
        host=DB_HOST,
        port=DB_PORT,
        database=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD
    )


    cur = conn.cursor()

    cur.execute("SELECT now()")
    db_time = cur.fetchone()

    print(f"database connection sucess! now time: {db_time[0]}")

    cur.close()
    conn.close()

except psycopg2.Error as e:
    print(f"database connect fail: {e}")
 