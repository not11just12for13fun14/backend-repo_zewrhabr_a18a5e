from pydantic import BaseModel, Field
from typing import Optional, List

class Problem(BaseModel):
    """
    Problem collection
    - title: short name of the problem
    - description: detailed statement
    - difficulty: easy | medium | hard
    - tags: list of topic tags
    - solution: optional reference solution text/markdown
    """
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=10)
    difficulty: str = Field("easy", pattern=r"^(easy|medium|hard)$")
    tags: List[str] = Field(default_factory=list)
    solution: Optional[str] = None

class Attempt(BaseModel):
    """
    Attempt collection for user tries and AI guidance transcript
    - problem_id: id string of the problem attempted
    - user_query: the user's attempt/question
    - ai_steps: list of guidance steps from AI
    - status: pending | solved | stuck
    """
    problem_id: str
    user_query: str
    ai_steps: List[str] = Field(default_factory=list)
    status: str = Field("pending", pattern=r"^(pending|solved|stuck)$")
