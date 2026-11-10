from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    roles: list[str]
    nombre: str


class UserMe(BaseModel):
    id: int
    email: EmailStr
    nombre: str
    roles: list[str]