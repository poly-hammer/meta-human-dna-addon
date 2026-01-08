from pathlib import Path
from typing import TYPE_CHECKING

from ..dna_io.misc import get_dna_component_type
from .body import MetaHumanComponentBody
from .head import MetaHumanComponentHead


if TYPE_CHECKING:
    from ..properties import MetahumanDnaImportProperties
    from ..rig_instance import RigInstance


def get_meta_human_component(
    file_path: Path,
    properties: "MetahumanDnaImportProperties",
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
