import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from bson.objectid import ObjectId

from database import db, create_document, get_documents
from schemas import Problem, Attempt

app = FastAPI(title="Solvix API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Helpers

def to_public(doc):
    if not doc:
        return doc
    d = dict(doc)
    if "_id" in d:
        d["id"] = str(d.pop("_id"))
    return d

class ProblemCreate(Problem):
    pass

class ProblemOut(Problem):
    id: str

class AttemptCreate(Attempt):
    pass

class AttemptOut(Attempt):
    id: str

@app.get("/")
def read_root():
    return {"message": "Solvix backend is running"}

@app.get("/test")
def test_database():
    status = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": "❌ Not Set",
        "database_name": "❌ Not Set",
        "collections": []
    }
    try:
        if db is not None:
            status["database"] = "✅ Connected"
            status["database_url"] = "✅ Set"
            status["database_name"] = getattr(db, 'name', 'unknown')
            try:
                status["collections"] = db.list_collection_names()[:10]
            except Exception:
                pass
    except Exception as e:
        status["database"] = f"❌ Error: {str(e)[:80]}"
    status["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    status["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"
    return status

# Problem Endpoints

@app.post("/api/problems", response_model=ProblemOut)
def create_problem(payload: ProblemCreate):
    try:
        new_id = create_document("problem", payload)
        doc = db["problem"].find_one({"_id": ObjectId(new_id)})
        return to_public(doc)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/problems", response_model=List[ProblemOut])
def list_problems(tag: Optional[str] = None, difficulty: Optional[str] = None, q: Optional[str] = None, limit: int = 50):
    filt = {}
    if tag:
        filt["tags"] = {"$in": [tag]}
    if difficulty:
        filt["difficulty"] = difficulty
    if q:
        filt["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"description": {"$regex": q, "$options": "i"}}
        ]
    docs = get_documents("problem", filt, limit)
    return [to_public(d) for d in docs]

@app.get("/api/problems/{problem_id}", response_model=ProblemOut)
def get_problem(problem_id: str):
    doc = db["problem"].find_one({"_id": ObjectId(problem_id)})
    if not doc:
        raise HTTPException(status_code=404, detail="Problem not found")
    return to_public(doc)

# Attempt Endpoints with simple AI guidance stub

class GuidanceRequest(BaseModel):
    problem_id: str
    user_query: str

class GuidanceResponse(BaseModel):
    attempt: AttemptOut
    next_hint: str

@app.post("/api/attempts/guidance", response_model=GuidanceResponse)
def get_guidance(payload: GuidanceRequest):
    # Very simple heuristic guidance to keep it self-contained
    problem = db["problem"].find_one({"_id": ObjectId(payload.problem_id)})
    if not problem:
        raise HTTPException(status_code=404, detail="Problem not found")

    desc = problem.get("description", "").lower()
    hint = "Break the problem into smaller steps: understand inputs, define outputs, and outline steps."

    if any(k in desc for k in ["array", "list"]):
        hint = "Consider iterating through the list, tracking required state (e.g., indices, sums)."
    if any(k in desc for k in ["graph", "node", "edge"]):
        hint = "Think about graph representations (adjacency list) and use BFS/DFS depending on shortest path vs traversal."
    if any(k in desc for k in ["dp", "dynamic", "subproblem"]):
        hint = "Try defining subproblems and a recurrence; memoize overlapping subproblems."

    attempt = Attempt(
        problem_id=payload.problem_id,
        user_query=payload.user_query,
        ai_steps=[hint],
        status="pending",
    )
    new_id = create_document("attempt", attempt)
    saved = db["attempt"].find_one({"_id": ObjectId(new_id)})
    attempt_pub = to_public(saved)
    return {"attempt": attempt_pub, "next_hint": hint}

# Schema endpoint for inspector tools
@app.get("/schema")
def get_schema_info():
    return {
        "collections": ["problem", "attempt"],
        "models": {
            "problem": Problem.model_json_schema(),
            "attempt": Attempt.model_json_schema(),
        }
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
