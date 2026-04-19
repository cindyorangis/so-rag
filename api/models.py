from pydantic import BaseModel


class AskRequest(BaseModel):
    question: str
    match_count: int = 12  # wider pool for reranker to work with
    model_id: str | None = None  # if None, use fallback chain


class Source(BaseModel):
    source: str
    page_number: int
    content: str
    section_title: str | None = None
    pdf_url: str | None = None


class AskResponse(BaseModel):
    answer: str
    sources: list[Source]
    mode: str = "answer"
    model_used: str | None = None


class FeedbackRequest(BaseModel):
    question: str
    answer: str
    rating: str  # "up" or "down"
    sources: list[dict] = []
    model_used: str | None = None