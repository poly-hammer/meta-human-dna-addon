from pathlib import Path
from typing import TYPE_CHECKING
from .head import MetaHumanComponentHead
from .body import MetaHumanComponentBody
from ..dna_io.misc import get_dna_component_type

if TYPE_CHECKING:
    from ..properties import MetahumanDnaImportProperties


def get_meta_human_component(
        file_path: Path, 
        properties: 'MetahumanDnaImportProperties'
    ) -> MetaHumanComponentHead | MetaHumanComponentBody:
    component_type = get_dna_component_type(file_path=file_path)
    if component_type == 'head':
        return MetaHumanComponentHead(
            dna_file_path=file_path,
            dna_import_properties=properties # type: ignore
        )
    elif component_type == 'body':
        return MetaHumanComponentBody(
            dna_file_path=file_path,
            dna_import_properties=properties # type: ignore
        )
    else:
        raise ValueError(f"Unsupported DNA component type: {component_type}")

__all__ = [
    'MetaHumanComponentHead',
    'MetaHumanComponentBody',
    'get_meta_human_component'
]