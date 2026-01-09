# standard library imports
from pathlib import Path

# local imports
from ..dna_io.misc import get_dna_component_type
from ..typing import *
from .body import MetaHumanComponentBody
from .head import MetaHumanComponentHead


def get_meta_human_component(
    file_path: Path,
    properties: "MetahumanImportProperties",
    name: str | None = None,
    rig_instance: "RigInstance | None" = None,
) -> MetaHumanComponentHead | MetaHumanComponentBody:
    component_type = get_dna_component_type(file_path=file_path)
    if component_type == "head":
        return MetaHumanComponentHead(
            name=name,
            dna_file_path=file_path,
            dna_import_properties=properties,
            rig_instance=rig_instance,
            component_type="head",
        )
    if component_type == "body":
        return MetaHumanComponentBody(
            name=name,
            dna_file_path=file_path,
            dna_import_properties=properties,
            rig_instance=rig_instance,
            component_type="body",
        )
    raise ValueError(f"Unsupported DNA component type: {component_type}")


__all__ = ["MetaHumanComponentBody", "MetaHumanComponentHead", "get_meta_human_component"]
