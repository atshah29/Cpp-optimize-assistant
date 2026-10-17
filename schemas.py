"""Validated API and project manifest contracts."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, field_validator, model_validator
from utils import relative_path


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Case(StrictModel):
    benchmark: bool = True
    name: str = Field(default="default", min_length=1, max_length=80)
    args: list[str] = Field(default_factory=list, max_length=30)
    stdin: str = Field(default="", max_length=65536)
    expected_stdout: str | None = Field(default=None, max_length=65536)
    expected_stderr: str | None = Field(default=None, max_length=65536)
    output_files: list[str] = Field(default_factory=list, max_length=10)

    @field_validator("output_files")
    @classmethod
    def paths(cls, values):
        return [relative_path(value) for value in values]

    @field_validator("args")
    @classmethod
    def argument_lengths(cls, values):
        if any(len(value) > 4096 or "\x00" in value for value in values):
            raise ValueError("Invalid or oversized argument")
        return values


class Options(StrictModel):
    mode: Literal["optimize", "benchmark", "compile"] = "optimize"
    build: Literal["simple", "cmake"] = "simple"
    standard: Literal["c++17", "c++20", "c++23"] = "c++17"
    sources: list[str] = Field(default_factory=list, max_length=100)
    include_dirs: list[str] = Field(default_factory=list, max_length=30)
    cmake_target: str = Field(default="", pattern=r"^[A-Za-z0-9_.+-]*$", max_length=100)
    executable: str = ""
    working_dir: str = "."
    cases: list[Case] = Field(default_factory=lambda: [Case()], min_length=1, max_length=8)
    attempts: int = Field(default=3, ge=1, le=5)
    repeats: int = Field(default=7, ge=5, le=15)
    min_improvement: float = Field(default=0.03, ge=0.01, le=0.5)
    run_timeout: int = Field(default=10, ge=1, le=30)
    profile: bool = True
    editable_files: list[str] = Field(default_factory=list, max_length=100)
    protected_main: dict[str, str] = Field(default_factory=dict, max_length=100)

    @field_validator("protected_main")
    @classmethod
    def protected_driver_text(cls, values):
        if sum(len(text.encode()) for text in values.values()) > 65536 or any(
            not text for text in values.values()
        ):
            raise ValueError("Protected driver fragments must be nonempty and total at most 64 KiB")
        return {relative_path(name): text for name, text in values.items()}

    @field_validator("sources", "include_dirs", "editable_files")
    @classmethod
    def paths(cls, values):
        return [relative_path(value) for value in values]

    @field_validator("working_dir", "executable")
    @classmethod
    def path(cls, value):
        return relative_path(value) if value else value

    @model_validator(mode="after")
    def valid_build(self):
        if self.build == "cmake" and (not self.cmake_target or not self.executable):
            raise ValueError(
                "CMake projects require cmake_target and executable (relative to the build directory)"
            )
        if len({case.name for case in self.cases}) != len(self.cases):
            raise ValueError("Workload names must be unique")
        if self.mode != "compile" and not any(case.benchmark for case in self.cases):
            raise ValueError("At least one workload must have benchmark=true")
        return self


class Edit(StrictModel):
    path: str = Field(min_length=1, max_length=300)
    old: str = Field(min_length=1, max_length=24000)
    new: str = Field(max_length=24000)


class Proposal(StrictModel):
    _metadata: dict = PrivateAttr(default_factory=dict)
    explanation: str = Field(min_length=1, max_length=3000)
    edits: list[Edit] = Field(default_factory=list, max_length=12)
