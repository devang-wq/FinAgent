from __future__ import annotations

from typing import Optional
from pydantic import BaseModel


class Entity(BaseModel):
    id: str
    name: str
    schema_type: Optional[str] = None
    datasets: list[str] = []


class Relationship(BaseModel):
    source_id: str
    target_id: str
    rel_type: str


class Document(BaseModel):
    id: str
    text: str
    entity_ids: list[str] = []
    score: Optional[float] = None


class SearchResult(BaseModel):
    query: str
    entities: list[Entity]
    documents: list[Document]


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str
    model: Optional[str] = None
