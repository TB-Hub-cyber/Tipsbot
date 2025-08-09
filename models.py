from pydantic import BaseModel, Field, HttpUrl
from typing import List

class SvsReq(BaseModel):
    url: HttpUrl
    debug: bool = False

class FootyReq(BaseModel):
    matchnr: int = Field(ge=1, le=13)
    url: HttpUrl
    debug: bool = False
