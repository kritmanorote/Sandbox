import os
from dotenv import load_dotenv

# Load .env BEFORE any Langfuse import so credentials are populated by the
# time Langfuse's module-level client picks them up.
load_dotenv()

from fastapi import FastAPI, HTTPException
from google.api_core.exceptions import ResourceExhausted, GoogleAPIError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
import google.generativeai as genai
from sqlalchemy import create_engine

from langchain_core.tools import tool
from langchain_core.documents import Document
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI, GoogleGenerativeAIEmbeddings
from langchain_postgres import PGVector
from langgraph.prebuilt import create_react_agent

from exchange_log import LoggedChatSession, summarize_langchain_result
from langfuse import get_client
from langfuse.langchain import CallbackHandler

# MLflow tracing — local-only for now (mlflow not in requirements.txt, so the
# Render deploy skips this). Enabled only when MLFLOW_TRACKING_URI is set.
if os.environ.get("MLFLOW_TRACKING_URI"):
    try:
        import mlflow

        mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])
        mlflow.set_experiment("sandbox-chat")
        mlflow.langchain.autolog()
    except Exception as e:
        # Observability setup must never take down the app. If the MLflow
        # tracking server is unreachable, log and continue without tracing.
        print(f"Warning: MLflow tracing disabled ({e})")

# OTel path to the same MLflow server — runs ALONGSIDE autolog so the same
# request produces two traces, one per pipeline, for fidelity comparison.
# Deliberately uses non-standard env var names: if we set the standard
# OTEL_EXPORTER_OTLP_TRACES_ENDPOINT, MLflow's own SDK also reads it and
# switches its export to OTLP/gRPC, silently breaking autolog.
if os.environ.get("MLFLOW_OTLP_ENDPOINT"):
    from opentelemetry import trace as otel_trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import BatchSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from openinference.instrumentation.langchain import LangChainInstrumentor

    _otel_provider = TracerProvider()
    _otel_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(
        endpoint=os.environ["MLFLOW_OTLP_ENDPOINT"],
        headers={"x-mlflow-experiment-id": os.environ.get("MLFLOW_OTLP_EXPERIMENT_ID", "1")},
    )))
    otel_trace.set_tracer_provider(_otel_provider)
    LangChainInstrumentor().instrument(tracer_provider=_otel_provider)

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


# ─── LangChain setup ───────────────────────────────────────────────────────
# Same embedding model the existing `chunks` table was seeded with — keeps
# retrieval quality comparable between /chat and /chat-langchain.
lc_embeddings = GoogleGenerativeAIEmbeddings(
    model="models/gemini-embedding-001",
    google_api_key=os.environ.get("GEMINI_API_KEY"),
)

# PGVector auto-creates `langchain_pg_collection` + `langchain_pg_embedding`
# tables in the same Neon DB. Distinct from the hand-rolled `chunks` table —
# the user can inspect both schemas side by side.
# Use a SQLAlchemy engine with pre_ping so stale Neon connections (idled out
# server-side) are detected and replaced before the query runs.
lc_engine = create_engine(
    os.environ["DATABASE_URL"],
    pool_pre_ping=True,
    pool_recycle=300,
)
lc_vectorstore = PGVector(
    embeddings=lc_embeddings,
    collection_name="chunks_lc",
    connection=lc_engine,
    use_jsonb=True,
)


def seed_langchain_chunks():
    """Seed CHUNKS into the LangChain PGVector collection once."""
    if not os.environ.get("GEMINI_API_KEY"):
        return
    conn = get_conn()
    cur = conn.cursor()
    try:
        cur.execute("""
            SELECT COUNT(*) FROM langchain_pg_embedding e
            JOIN langchain_pg_collection c ON e.collection_id = c.uuid
            WHERE c.name = 'chunks_lc'
        """)
        if cur.fetchone()[0] > 0:
            return
    except psycopg2.errors.UndefinedTable:
        conn.rollback()  # tables don't exist yet — PGVector will create them
    finally:
        cur.close()
        conn.close()
    try:
        lc_vectorstore.add_documents([Document(page_content=c) for c in CHUNKS])
        print(f"Seeded {len(CHUNKS)} chunks into LangChain PGVector collection.")
    except Exception as e:
        print(f"Warning: LangChain chunk seeding failed: {e}")


seed_langchain_chunks()


@tool
def search_knowledge_base_lc(query: str) -> list[str]:
    """Search the project knowledge base for facts about Neon Dash, Pacman,
    ghosts, leaderboard, backend, frontend, mobile controls, or the chat
    feature. Call this whenever the user asks about this project."""
    docs = lc_vectorstore.similarity_search(query, k=2)
    return [doc.page_content for doc in docs]


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
    session_id: Optional[str] = None  # client-generated; groups multi-turn traces in Langfuse Sessions

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
        "gemini-3.1-flash-lite",
        system_instruction=req.system_instruction or None,
        tools=tools or None
    )
    history = [
        {"role": m.role, "parts": [m.content]}
        for m in req.messages[:-1]
    ]

    last_msg = req.messages[-1].content
    tool_calls_log = []

    try:
        session = LoggedChatSession(model, history)
        response = session.send_text(last_msg)

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
                response = session.send_function_response(fc.name, {"results": chunks})

        return {"reply": response.text, "tool_calls": tool_calls_log, "exchange_log": session.log}

    except ResourceExhausted:
        raise HTTPException(status_code=429, detail="Gemini API rate limit reached. Try again later.")
    except GoogleAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))


@app.post("/chat-langchain")
def chat_langchain(req: ChatRequest):
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="AI service not configured")

    # If a LiteLLM gateway is configured, route through it instead of calling
    # Gemini directly. The app then speaks OpenAI's protocol to the proxy and
    # holds the PROXY key — the real Gemini key lives only inside the proxy.
    proxy_url = os.environ.get("LITELLM_PROXY_URL")
    proxy_key = os.environ.get("LITELLM_PROXY_KEY")
    if proxy_url:
        # Fail closed: if the gateway is enabled but no key is configured, refuse
        # the request rather than silently falling back to a privileged default.
        if not proxy_key:
            raise HTTPException(status_code=503, detail="Gateway enabled but LITELLM_PROXY_KEY is not set")
        from langchain_openai import ChatOpenAI
        model = ChatOpenAI(
            model="chat-model",                              # the proxy's alias, not "gemini-..."
            base_url=proxy_url,                              # the choke point
            api_key=proxy_key,                               # per-app virtual key, supplied via env
        )
    else:
        model = ChatGoogleGenerativeAI(
            model="gemini-3.1-flash-lite",
            google_api_key=api_key,
        )
    tools = [search_knowledge_base_lc] if req.use_agent else []
    agent = create_react_agent(model, tools=tools)

    # Translate the frontend's history into LangChain message types.
    messages = []
    if req.system_instruction:
        messages.append(SystemMessage(content=req.system_instruction))
    for m in req.messages:
        if m.role == "user":
            messages.append(HumanMessage(content=m.content))
        elif m.role == "model":
            messages.append(AIMessage(content=m.content))

    # Initialize the Langfuse Callback Handler
    langfuse_handler = CallbackHandler()

    try:
        result = agent.invoke(
            {"messages": messages},
            config={
                "callbacks": [langfuse_handler],
                "run_name": "chat-langchain",  # becomes the trace name in Langfuse
                "metadata": {
                    # langfuse_ prefixed keys are picked up by the CallbackHandler
                    "langfuse_session_id": req.session_id,
                    "langfuse_tags": ["chat-langchain", "agent" if req.use_agent else "no-agent"],
                },
            },
        )
        # Flush to guarantee delivery in a request-response context
        get_client().flush()

        
        reply, tool_calls_log, exchange_log = summarize_langchain_result(result, len(messages))
        return {"reply": reply, "tool_calls": tool_calls_log, "exchange_log": exchange_log}

    except ResourceExhausted:
        raise HTTPException(status_code=429, detail="Gemini API rate limit reached. Try again later.")
    except GoogleAPIError as e:
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        import traceback
        with open("error_traceback.txt", "w") as f:
            traceback.print_exc(file=f)
        raise e



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
