import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import psycopg2
import google.generativeai as genai

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CHUNKS = [
    "Neon Dash is a side-scrolling obstacle game built with Phaser 3. The player controls a neon character that must dodge incoming obstacles. Scores are saved to a leaderboard via the FastAPI backend.",
    "Pacman is a maze game rewritten from scratch in JavaScript Canvas (no libraries). It has four ghosts: Red, Pink, Cyan, and Orange, each with unique scatter corner targets.",
    "Ghosts in Pacman have four AI modes: scatter (head to corner), chase (target Pacman), frightened (turn blue, move randomly after Pacman eats a power pellet), and eaten (return to ghost house).",
    "The leaderboard stores top scores in a Neon PostgreSQL database. The query groups by player name and returns MAX(score) per player, showing only the top 5.",
    "The backend is built with FastAPI and deployed on Render (free tier). It handles leaderboard reads/writes and proxies AI requests to the Gemini API to keep the API key server-side.",
    "The frontend is built with React and Vite, deployed as a static site on Render. Game pages (Neon Dash, Pacman, Chat) are standalone HTML files in the public folder.",
    "Mobile controls for Pacman include a D-pad overlay (visible only on touch devices via CSS pointer:coarse media query) and swipe gesture detection on the canvas element.",
    "The Neon Chat page is a standalone HTML file. It keeps conversation history in a JS array on the client and sends the full history to the backend on every message for multi-turn context.",
    "The project uses a Render Blueprint (render.yaml) to define both the web service (backend) and static site (frontend) so they can be deployed together from one GitHub repo.",
]

# Tool definition given to Gemini — describes what the function does and what args it takes
SEARCH_TOOL = genai.protos.Tool(
    function_declarations=[
        genai.protos.FunctionDeclaration(
            name="search_knowledge_base",
            description="Search the project knowledge base for facts about Neon Dash, Pacman, ghosts, leaderboard, backend, frontend, mobile controls, or the chat feature. Call this whenever the user asks about this project.",
            parameters=genai.protos.Schema(
                type=genai.protos.Type.OBJECT,
                properties={
                    "query": genai.protos.Schema(
                        type=genai.protos.Type.STRING,
                        description="The search query"
                    )
                },
                required=["query"]
            )
        )
    ]
)


def get_conn():
    return psycopg2.connect(os.environ["DATABASE_URL"])


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leaderboard (
            id SERIAL PRIMARY KEY,
            name VARCHAR(32) NOT NULL,
            score INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS chunks (
            id SERIAL PRIMARY KEY,
            content TEXT NOT NULL,
            embedding vector(3072)
        )
    """)
    conn.commit()
    cur.close()
    conn.close()


def seed_chunks():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        return
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM chunks")
    if cur.fetchone()[0] > 0:
        cur.close()
        conn.close()
        return
    try:
        genai.configure(api_key=api_key)
        result = genai.embed_content(
            model="models/gemini-embedding-001",
            content=CHUNKS,
            task_type="RETRIEVAL_DOCUMENT"
        )
        for chunk, emb in zip(CHUNKS, result["embedding"]):
            vec_str = '[' + ','.join(map(str, emb)) + ']'
            cur.execute(
                "INSERT INTO chunks (content, embedding) VALUES (%s, %s::vector)",
                (chunk, vec_str)
            )
        conn.commit()
        print(f"Seeded {len(CHUNKS)} chunks into database.")
    except Exception as e:
        print(f"Warning: chunk seeding failed: {e}")
    finally:
        cur.close()
        conn.close()


def do_search(query: str, top_k: int = 2, threshold: float = 0.5):
    """Embed query and search chunks table by cosine similarity."""
    result = genai.embed_content(
        model="models/gemini-embedding-001",
        content=query,
        task_type="RETRIEVAL_QUERY"
    )
    query_vec = result["embedding"]
    vec_str = '[' + ','.join(map(str, query_vec)) + ']'
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        SELECT content, embedding::text, 1 - (embedding <=> %s::vector) AS score
        FROM chunks
        WHERE 1 - (embedding <=> %s::vector) > %s
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """, (vec_str, vec_str, threshold, vec_str, top_k))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return query_vec, [
        {
            "chunk": r[0],
            "vector": [float(x) for x in r[1].strip('[]').split(',')],
            "score": float(r[2])
        }
        for r in rows
    ]


init_db()
seed_chunks()


class ScoreEntry(BaseModel):
    name: str
    score: int


class ChatMessage(BaseModel):
    role: str
    content: str

class ChatRequest(BaseModel):
    messages: List[ChatMessage]
    system_instruction: str = ""
    use_agent: bool = False

class SearchRequest(BaseModel):
    query: str
    top_k: int = 2
    threshold: float = 0.5


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


@app.post("/search")
def search(req: SearchRequest):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")
    try:
        genai.configure(api_key=api_key)
        query_vec, results = do_search(req.query, req.top_k, req.threshold)
        return {"query_vector": query_vec, "results": results}
    except ResourceExhausted:
        raise HTTPException(status_code=429, detail="Gemini API rate limit reached. Try again later.")
    except GoogleAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/chat")
def chat(req: ChatRequest):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")
    genai.configure(api_key=api_key)

    tools = [SEARCH_TOOL] if req.use_agent else []
    model = genai.GenerativeModel(
        "gemini-2.5-flash",
        system_instruction=req.system_instruction or None,
        tools=tools or None
    )
    history = [
        {"role": m.role, "parts": [m.content]}
        for m in req.messages[:-1]
    ]

    try:
        chat_session = model.start_chat(history=history)
        response = chat_session.send_message(req.messages[-1].content)
        tool_calls_log = []

        # ReAct loop: keep running until Gemini gives a text response
        for _ in range(5):
            fn_part = next(
                (p for p in response.candidates[0].content.parts if p.function_call.name),
                None
            )
            if not fn_part:
                break

            fc = fn_part.function_call
            if fc.name == "search_knowledge_base":
                query = fc.args["query"]
                _, results = do_search(query)
                chunks = [r["chunk"] for r in results]
                tool_calls_log.append({"query": query, "results": chunks})

                # Send tool result back so Gemini can continue reasoning
                response = chat_session.send_message(
                    genai.protos.Content(
                        parts=[genai.protos.Part(
                            function_response=genai.protos.FunctionResponse(
                                name=fc.name,
                                response={"results": chunks}
                            )
                        )]
                    )
                )

        return {"reply": response.text, "tool_calls": tool_calls_log}

    except ResourceExhausted:
        raise HTTPException(status_code=429, detail="Gemini API rate limit reached. Try again later.")
    except GoogleAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


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
