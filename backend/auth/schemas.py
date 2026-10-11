"""Request validation for authentication and registration."""

import re

from pydantic import BaseModel, EmailStr, Field, SecretStr, field_validator


class EmailInput(BaseModel):
    email: EmailStr = Field(max_length=255)

    @field_validator("email")
    @classmethod
    def normalize(cls, value):
        return str(value).strip().lower()


class NewPassword(BaseModel):
    password: SecretStr = Field(min_length=8, max_length=20)

    @field_validator("password")
    @classmethod
    def validate_password(cls, value):
        if not re.fullmatch(r"[A-Za-z0-9]{8,20}", value.get_secret_value()):
            raise ValueError("密码须为 8–20 个字符，只能包含数字和英文字母。")
        return value


class Credentials(EmailInput, NewPassword):
    pass


class RegistrationInput(Credentials):
    pass


class RegistrationHandleInput(EmailInput):
    registration_token: SecretStr = Field(min_length=32, max_length=128)


class RegistrationCodeInput(RegistrationHandleInput):
    code: SecretStr = Field(min_length=6, max_length=6)

    @field_validator("code")
    @classmethod
    def validate_code(cls, value):
        if not re.fullmatch(r"[0-9]{6}", value.get_secret_value()):
            raise ValueError("验证码须为 6 位数字。")
        return value


class PasswordResetInput(NewPassword):
    token: str = Field(min_length=32, max_length=128)
