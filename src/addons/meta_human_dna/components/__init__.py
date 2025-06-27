from pathlib import Path
from typing import TYPE_CHECKING
from .head import MetaHumanComponentHead
from .body import MetaHumanComponentBody
from ..dna_io.misc import get_dna_component_type

if TYPE_CHECKING:
    from ..properties import MetahumanDnaImportProperties
    from ..rig_logic import RigLogicInstance


def get_meta_human_component(
        file_path: Path, 
        properties: 'MetahumanDnaImportProperties',
        name: str | None = None,
        rig_logic_instance: 'RigLogicInstance | None' = None,
    ) -> MetaHumanComponentHead | MetaHumanComponentBody:
    component_type = get_dna_component_type(file_path=file_path)
    if component_type == 'head':
        return MetaHumanComponentHead(
            name=name,
            dna_file_path=file_path,
            dna_import_properties=properties,
            rig_logic_instance=rig_logic_instance,
            component_type='head'
        )
    elif component_type == 'body':
        return MetaHumanComponentBody(
            name=name,
            dna_file_path=file_path,
            dna_import_properties=properties,
            rig_logic_instance=rig_logic_instance,
            component_type='body'
        )
    else:
        raise ValueError(f"Unsupported DNA component type: {component_type}")

__all__ = [
    'MetaHumanComponentHead',
    'MetaHumanComponentBody',
    'get_meta_human_component'
]