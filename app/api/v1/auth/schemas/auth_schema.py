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
    driver_linked: bool = False       # True only when a Driver record has user = this email
    driver_ids: list[str] = []        # the Driver records (HR-DRI-...) the driver tabs will use


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
