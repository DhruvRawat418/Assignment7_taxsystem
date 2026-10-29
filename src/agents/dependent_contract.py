"""Transcribed dependent details for the assignment subset; no credit inference."""
from pydantic import BaseModel, ConfigDict, Field

class DependentDetails(BaseModel):
    model_config = ConfigDict(extra='forbid')
    first_name: str = Field(min_length=1, max_length=60)
    last_name: str = Field(min_length=1, max_length=60)
    ssn: str = Field(pattern=r'^9[0-9]{2}-[0-9]{2}-[0-9]{4}$')
    relationship: str = Field(min_length=1, max_length=40)
    sources: dict
