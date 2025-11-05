import datetime
import uuid

from pydantic import EmailStr, model_validator
from sqlmodel import Field, SQLModel

from app.core.security import get_password_hash
from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class UserBase(Base):
    email: EmailStr = Field(unique=True, index=True, max_length=255)
    phone: str | None = Field(default=None, max_length=255)
    is_active: bool = Field(default=True)
    is_superuser: bool = Field(default=False)
    full_name: str | None = Field(default=None, max_length=255)
    is_verified: bool = Field(default=False)
    is_verification_email_sent: bool = Field(default=False)
    last_verification_email_sent: datetime.datetime | None = Field(default=None)


class UserCreate(UserBase, BaseCreate):
    password: str = Field(..., min_length=8, max_length=128)
    hashed_password: str | None = Field(default=None, exclude=True)  # Auto-généré

    @model_validator(mode="after")
    def hash_password(self):
        """
        Automatically hash password when creating a user.
        """
        if self.password and not self.hashed_password:
            self.hashed_password = get_password_hash(self.password)
        return self


class UserUpdate(BaseUpdate):
    email: EmailStr | None = None
    phone: str | None = None
    full_name: str | None = None
    is_active: bool | None = None
    is_superuser: bool | None = None
    is_verified: bool | None = None
    password: str | None = Field(default=None, min_length=8, max_length=128)
    hashed_password: str | None = Field(default=None, exclude=True)  # Auto-généré

    @model_validator(mode="after")
    def hash_password(self):
        """
        Automatically hash password when updating a user.
        """
        if self.password and not self.hashed_password:
            self.hashed_password = get_password_hash(self.password)
        return self


class UserPasswordUpdate(SQLModel):
    current_password: str = Field(
        ..., min_length=1, description="Current password for verification"
    )
    new_password: str = Field(
        ..., min_length=8, max_length=128, description="New password"
    )
    confirm_password: str = Field(
        ..., min_length=8, max_length=128, description="Confirm new password"
    )
    hashed_password: str | None = Field(default=None, exclude=True)  # Auto-généré

    @model_validator(mode="after")
    def hash_password(self):
        """
        Automatically hash password when updating a user.
        """
        if self.new_password and not self.hashed_password:
            self.hashed_password = get_password_hash(self.new_password)
        return self


class UserPasswordReset(SQLModel):
    email: EmailStr = Field(..., description="Email address for password reset")


class UserPasswordResetConfirm(SQLModel):
    token: str = Field(..., description="Password reset token")
    new_password: str = Field(
        ..., min_length=8, max_length=128, description="New password"
    )
    confirm_password: str = Field(
        ..., min_length=8, max_length=128, description="Confirm new password"
    )


class UserEmailVerification(SQLModel):
    email: EmailStr = Field(..., description="Email to verify")


class UserEmailVerificationConfirm(SQLModel):
    token: str = Field(..., description="Email verification token")


class UserLogin(SQLModel):
    email: EmailStr = Field(..., description="User email")
    password: str = Field(..., description="User password")


class User(UserBase, table=True):
    __tablename__ = "users"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    hashed_password: str = Field(..., max_length=128)
    password_reset_token: str | None = Field(default=None, max_length=255)
    password_reset_token_expires: datetime.datetime | None = Field(default=None)
    email_verification_token: str | None = Field(default=None, max_length=255)
    email_verification_token_expires: datetime.datetime | None = Field(default=None)
    failed_login_attempts: int = Field(default=0)
    locked_until: datetime.datetime | None = Field(default=None)
    last_login: datetime.datetime | None = Field(default=None)


class UserPublic(UserBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    last_login: datetime.datetime | None = None


class UserProfile(SQLModel):
    id: uuid.UUID
    email: EmailStr
    full_name: str | None = None
    phone: str | None = None
    is_verified: bool
    last_login: datetime.datetime | None = None
    created_at: datetime.datetime | None = None


class UserAdminView(UserBase, BasePublic):
    id: uuid.UUID
    failed_login_attempts: int
    locked_until: datetime.datetime | None = None
    last_login: datetime.datetime | None = None
    password_reset_token_expires: datetime.datetime | None = None
    email_verification_token_expires: datetime.datetime | None = None


class UsersPublic(SQLModel):
    data: list[UserPublic] = Field(default_factory=list, description="List of users")
    count: int = Field(default=0, description="Total number of users")


# Contents of JWT token
class TokenPayload(SQLModel):
    sub: str | None = None


# JSON payload containing access token
class Token(SQLModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int  # Seconds until access token expires


class RefreshTokenRequest(SQLModel):
    refresh_token: str


class NewPassword(SQLModel):
    token: str
    new_password: str = Field(min_length=8, max_length=40)


class EmailValidation(SQLModel):
    token: str
