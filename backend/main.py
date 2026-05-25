import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import psycopg2

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_db_version():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()
    cur.execute("SELECT version();")
    version = cur.fetchone()[0]
    cur.close()
    conn.close()
    return version


@app.get("/")
def root():
    return {"message": "Hello, World!"}


@app.get("/health")
def health():
    try:
        db_version = get_db_version()
        return {"status": "ok", "db": db_version}
    except Exception as e:
        return {"status": "ok", "db": f"error: {str(e)}"}
