from pydantic import BaseModel, Field, field_validator


class DebugInfo(BaseModel):
    step: str | None = None
    current_url: str | None = None
    page_title: str | None = None
    timestamp: str | None = None
    screenshot: str | None = None
    browser_headless: bool | None = None
    user_data_dir: str | None = None
    possible_reason: str | None = None
    next_action: str | None = None
    visible_markers: list[str] = Field(default_factory=list)
    exception_type: str | None = None
    exception_message: str | None = None


class LoginResponse(BaseModel):
    status: str
    message: str
    current_url: str | None = None
    handled_modals: list[str] | None = None
    screenshot: str | None = None
    failed_step: str | None = None
    steps: list["StepResult"] | None = None
    debug: DebugInfo | None = None


class StepResult(BaseModel):
    step: str
    status: str
    message: str | None = None
    value: str | None = None
    selected_kit: str | None = None
    matched_display_url: str | None = None
    scan_status: str | None = None


class AddAppRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class AddAppResponse(BaseModel):
    status: str
    message: str
    input_url: str | None = None
    selected_kit: str | None = None
    current_url: str | None = None
    screenshot: str | None = None
    steps: list[StepResult] = Field(default_factory=list)
    next_action: dict | None = None
    debug: DebugInfo | None = None


class MapperDefaultResponse(BaseModel):
    default_experience_kit: str
    mode: str


class MapperResolveRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class MapperResolveResponse(BaseModel):
    url: str
    experience_kit: str
    mode: str


class FilterCodeRequest(BaseModel):
    url: str

    @field_validator("url")
    @classmethod
    def url_must_be_http(cls, v: str) -> str:
        if not v.startswith(("http://", "https://")):
            raise ValueError("url must start with http:// or https://")
        return v


class FilterCodeResponse(BaseModel):
    status: str
    message: str
    input_url: str
    normalized_domain: str | None = None
    matched_display_url: str | None = None
    scan_status: str | None = None
    data_domain_script: str | None = None
    script_snippet: str | None = None
    current_url: str | None = None
    screenshot: str | None = None
    steps: list[StepResult] = Field(default_factory=list)
    debug: DebugInfo | None = None


class AuthStatusResponse(BaseModel):
    status: str
    message: str
    current_url: str | None = None


LoginResponse.model_rebuild()
