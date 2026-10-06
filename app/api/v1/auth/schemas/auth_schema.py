from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1)


class OtpRequest(BaseModel):
    email: EmailStr


class OtpVerifyRequest(BaseModel):
    email: EmailStr
    otp: str = Field(min_length=6, max_length=6, pattern=r"^\d{6}$")


class UserInfo(BaseModel):
    name: str
    email: str
    full_name: str
    mobile_no: str = ""
    roles: list[str]
    primary_role: str


class LoginResponse(BaseModel):
    success: bool = True
    message: str = "Login Successful"
    token: str
    token_type: str = "bearer"
    user: UserInfo


class OtpRequestResponse(BaseModel):
    success: bool = True
    message: str
    expires_in_seconds: int
