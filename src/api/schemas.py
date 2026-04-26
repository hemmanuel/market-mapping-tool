from typing import List, Optional
from pydantic import BaseModel, Field

class Entity(BaseModel):
    name: str

class Relationship(BaseModel):
    source: str
    type: str
    target: str

class DataSourceSchema(BaseModel):
    type: str
    url: str
    name: str

class SchemaConfig(BaseModel):
    entities: List[str]
    relationships: List[Relationship]

class PipelineConfig(BaseModel):
    currentStep: str
    niche: Optional[str] = None
    schema_config: Optional[SchemaConfig] = Field(None, alias="schema")
    sources: List[DataSourceSchema] = []
