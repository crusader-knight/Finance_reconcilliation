from typing import Literal

from pydantic import BaseModel, Field


class DemoRequest(BaseModel):
    records: int = Field(default=120, ge=10, le=5000)
    anomaly_rate: float = Field(default=0.16, ge=0, le=0.8)
    seed: int = 42


class ReviewRequest(BaseModel):
    decision: Literal["APPROVE", "REJECT"]
    comment: str = Field(min_length=2, max_length=1000)


class BatchResponse(BaseModel):
    id: str
    name: str
    status: str


class UploadResponse(BaseModel):
    batch_id: str
    source_type: str
    accepted: int
    rejected: int
