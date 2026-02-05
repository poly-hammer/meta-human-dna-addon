from .constants import ToolInfo


DOCUMENTATION_URL = "https://docs.polyhammer.com/meta-human-dna-addon/"


def manual_map() -> tuple[str, tuple[tuple[str, str], ...]]:
    manual_mapping = (
        (f"bpy.ops.{ToolInfo.NAME}.convert_selected_to_dna", "user-interface/utilities/#convert-selected-to-dna"),
    )
    return (DOCUMENTATION_URL, manual_mapping)
