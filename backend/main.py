import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import psycopg2

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard (
            id SERIAL PRIMARY KEY,
            name VARCHAR(32) NOT NULL,
            score INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


init_db()


class ScoreEntry(BaseModel):
    name: str
    score: int


@app.get("/")
def root():
    return {"message": "Hello, World!"}


@app.get("/health")
def health():
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]
        cur.close()
        conn.close()
        return {"status": "ok", "db": version}
    except Exception as e:
        return {"status": "ok", "db": f"error: {str(e)}"}


@app.post("/leaderboard")
def submit_score(entry: ScoreEntry):
    if not entry.name.strip():
        raise HTTPException(status_code=400, detail="Name is required")
    if entry.score < 0:
        raise HTTPException(status_code=400, detail="Invalid score")
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO leaderboard (name, score) VALUES (%s, %s) RETURNING id",
        (entry.name.strip()[:32], entry.score)
    )
    new_id = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()
    return {"id": new_id, "name": entry.name, "score": entry.score}


@app.get("/leaderboard")
def get_leaderboard():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "SELECT name, MAX(score) as score FROM leaderboard GROUP BY name ORDER BY score DESC LIMIT 5"
    )
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [{"name": r[0], "score": r[1]} for r in rows]
