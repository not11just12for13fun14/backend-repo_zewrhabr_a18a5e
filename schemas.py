"""
Database Schemas for Solvix

Each Pydantic model represents a MongoDB collection. The collection name is the
lowercase of the class name (e.g., Session -> "session").
"""
from pydantic import BaseModel, Field
from typing import List, Optional

class Problem(BaseModel):
    title: str = Field(..., description="Short title for the problem")
    description: str = Field(..., description="Detailed problem statement")
    category: str = Field("general", description="Category: coding, math, writing, general, etc.")
    difficulty: str = Field("medium", description="Difficulty: easy, medium, hard")

class GuidanceStep(BaseModel):
    index: int = Field(..., description="Step order starting at 1")
    text: str = Field(..., description="Actionable step text")
    status: str = Field("pending", description="pending | in_progress | done")
    note: Optional[str] = Field(None, description="Optional note or reasoning")

class Session(BaseModel):
    problem_id: Optional[str] = Field(None, description="Reference to problem document id")
    problem_title: str = Field(..., description="Cached title for quick access")
    problem_description: str = Field(..., description="Cached description")
    category: str = Field("general")
    difficulty: str = Field("medium")
    steps: List[GuidanceStep] = Field(default_factory=list)
    current_step: int = Field(1, description="1-based index of current step")

class Message(BaseModel):
    session_id: str = Field(..., description="Reference to session id")
    role: str = Field(..., description="user | assistant | system")
    content: str = Field(..., description="Message text")
