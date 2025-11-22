import os
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
from bson import ObjectId

from database import db, create_document, get_documents
from schemas import Problem, Session, GuidanceStep, Message

app = FastAPI(title="Solvix API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# -----------------------------
# Helpers
# -----------------------------

def to_str_id(doc: Dict[str, Any]):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    # Convert nested ObjectIds if any
    for k, v in d.items():
        if isinstance(v, ObjectId):
            d[k] = str(v)
        if isinstance(v, list):
            d[k] = [str(x) if isinstance(x, ObjectId) else x for x in v]
    return d


def collection_name(model_cls) -> str:
    return model_cls.__name__.lower()


def generate_guidance_steps(description: str, category: str = "general") -> List[GuidanceStep]:
    """Simple deterministic guidance generator as an AI stand-in."""
    base = [
        "Clarify the goal and constraints. Summarize the problem in your own words.",
        "Break the problem into smaller sub-parts. Identify inputs, outputs, and edge cases.",
        "Draft a step-by-step approach or outline to solve each sub-part.",
        "Execute the plan: implement or compute the solution incrementally.",
        "Test with examples, review results, and refine any weak points.",
    ]

    cat_tips = {
        "coding": "Consider time/space complexity and write unit tests.",
        "math": "Write definitions, known theorems, and try a simple case first.",
        "writing": "Define audience, tone, and structure (intro, body, conclusion).",
        "general": "Stay focused on the main objective and time-box explorations.",
    }
    tip = cat_tips.get(category, cat_tips["general"])  # default

    steps: List[GuidanceStep] = []
    for i, text in enumerate(base, start=1):
        note = tip if i in (2, 4) else None
        steps.append(GuidanceStep(index=i, text=text, status="pending", note=note))

    # Optional customization based on description length
    if len(description.split()) > 60:
        steps.append(GuidanceStep(index=len(steps) + 1, text="Create a brief summary of the solution and next steps.", status="pending"))
    return steps


# -----------------------------
# Request Models
# -----------------------------

class CreateProblem(BaseModel):
    title: str
    description: str
    category: str = Field("general")
    difficulty: str = Field("medium")


class CreateSession(BaseModel):
    problem_id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    category: str = Field("general")
    difficulty: str = Field("medium")
    auto_generate_steps: bool = Field(True)


class UpdateStep(BaseModel):
    status: Optional[str] = None
    note: Optional[str] = None


class CreateMessage(BaseModel):
    role: str
    content: str


# -----------------------------
# Routes: Health & Info
# -----------------------------

@app.get("/")
def read_root():
    return {"message": "Solvix Backend Running"}


@app.get("/api/hello")
def hello():
    return {"message": "Hello from Solvix API"}


@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "connection_status": "Not Connected",
        "collections": [],
    }
    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
            response["database_name"] = db.name if hasattr(db, "name") else "✅ Set"
            try:
                cols = db.list_collection_names()
                response["collections"] = cols
                response["database"] = "✅ Connected & Working"
                response["connection_status"] = "Connected"
            except Exception as e:
                response["database"] = f"⚠️ Connected but Error: {str(e)[:80]}"
        else:
            response["database"] = "⚠️ Available but not initialized"
    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:100]}"
    return response


@app.get("/schema")
def get_schema():
    return {
        "problem": Problem.model_json_schema(),
        "session": Session.model_json_schema(),
        "guidancestep": GuidanceStep.model_json_schema(),
        "message": Message.model_json_schema(),
    }


# -----------------------------
# Routes: Problems
# -----------------------------

@app.post("/api/problems")
def create_problem(payload: CreateProblem):
    coll = collection_name(Problem)
    problem = Problem(**payload.model_dump())
    inserted_id = create_document(coll, problem)
    doc = db[coll].find_one({"_id": ObjectId(inserted_id)})
    return to_str_id(doc)


@app.get("/api/problems")
def list_problems(limit: int = 50):
    coll = collection_name(Problem)
    docs = get_documents(coll, {}, min(limit, 200))
    return [to_str_id(d) for d in docs]


# -----------------------------
# Routes: Sessions
# -----------------------------

@app.post("/api/sessions")
def create_session(payload: CreateSession):
    # Resolve source problem
    src_title = payload.title
    src_desc = payload.description
    category = payload.category
    difficulty = payload.difficulty

    if payload.problem_id:
        prob = db[collection_name(Problem)].find_one({"_id": ObjectId(payload.problem_id)})
        if not prob:
            raise HTTPException(404, "Problem not found")
        src_title = prob.get("title")
        src_desc = prob.get("description")
        category = prob.get("category", category)
        difficulty = prob.get("difficulty", difficulty)

    if not src_title or not src_desc:
        raise HTTPException(400, "Provide either problem_id or title+description")

    session_doc = Session(
        problem_id=str(payload.problem_id) if payload.problem_id else None,
        problem_title=src_title,
        problem_description=src_desc,
        category=category,
        difficulty=difficulty,
        steps=[],
        current_step=1,
    ).model_dump()

    # Insert session
    sid = db[collection_name(Session)].insert_one(session_doc).inserted_id

    # Optionally generate steps
    if payload.auto_generate_steps:
        steps = [s.model_dump() for s in generate_guidance_steps(src_desc, category)]
        for s in steps:
            s.pop("index", None)  # we'll store order by array position
        db[collection_name(Session)].update_one({"_id": sid}, {"$set": {"steps": steps}})

    doc = db[collection_name(Session)].find_one({"_id": sid})
    return to_str_id(doc)


@app.get("/api/sessions/{session_id}")
def get_session(session_id: str):
    doc = db[collection_name(Session)].find_one({"_id": ObjectId(session_id)})
    if not doc:
        raise HTTPException(404, "Session not found")
    # Attach messages
    msgs = list(db[collection_name(Message)].find({"session_id": session_id}).sort("_id", 1))
    out = to_str_id(doc)
    out["steps"] = out.get("steps", [])
    out["messages"] = [to_str_id(m) for m in msgs]
    # Recompute human-friendly index on read
    for i, st in enumerate(out["steps"], start=1):
        st["index"] = i
    return out


@app.post("/api/sessions/{session_id}/steps/generate")
def generate_steps(session_id: str):
    doc = db[collection_name(Session)].find_one({"_id": ObjectId(session_id)})
    if not doc:
        raise HTTPException(404, "Session not found")
    steps = [s.model_dump() for s in generate_guidance_steps(doc.get("problem_description", ""), doc.get("category", "general"))]
    for s in steps:
        s.pop("index", None)
    db[collection_name(Session)].update_one({"_id": ObjectId(session_id)}, {"$set": {"steps": steps, "current_step": 1}})
    return {"ok": True}


@app.patch("/api/sessions/{session_id}/steps/{step_index}")
def update_step(session_id: str, step_index: int, payload: UpdateStep):
    doc = db[collection_name(Session)].find_one({"_id": ObjectId(session_id)})
    if not doc:
        raise HTTPException(404, "Session not found")
    steps = doc.get("steps", [])
    if step_index < 1 or step_index > len(steps):
        raise HTTPException(400, "Invalid step index")
    idx = step_index - 1
    if payload.status is not None:
        steps[idx]["status"] = payload.status
    if payload.note is not None:
        steps[idx]["note"] = payload.note
    db[collection_name(Session)].update_one({"_id": ObjectId(session_id)}, {"$set": {"steps": steps}})
    return {"ok": True}


@app.post("/api/sessions/{session_id}/messages")
def add_message(session_id: str, payload: CreateMessage):
    # Ensure session exists
    doc = db[collection_name(Session)].find_one({"_id": ObjectId(session_id)})
    if not doc:
        raise HTTPException(404, "Session not found")
    msg = Message(session_id=session_id, role=payload.role, content=payload.content)
    mid = create_document(collection_name(Message), msg)
    return {"id": mid}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
