"""Read the YAML planning files and check them against the models."""

from pathlib import Path

import yaml
from pydantic import BaseModel

from planner.models import AccommodationFile, Constraints, OptionsFile


def load_model[ModelT: BaseModel](path: Path, model: type[ModelT]) -> ModelT:
    """Parse one YAML file and validate it. Raises ValidationError on bad data."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return model.model_validate(data)


def load_constraints(path: Path) -> Constraints:
    return load_model(path, Constraints)


def load_accommodation(path: Path) -> AccommodationFile:
    return load_model(path, AccommodationFile)


def load_options(path: Path) -> OptionsFile:
    return load_model(path, OptionsFile)
