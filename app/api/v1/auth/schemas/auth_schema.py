from pydantic import BaseModel

class LoginRequest(BaseModel):
    usr: str
    pwd: str