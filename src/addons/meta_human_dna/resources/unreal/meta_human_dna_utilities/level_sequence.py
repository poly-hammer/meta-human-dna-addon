import unreal
from typing import Any, Dict, List, Tuple, Optional
from meta_human_dna_utilities import content_browser, level

def _get_binding_path(
        binding: Any, 
        name:Optional[str] = None
    ) -> Optional[str]:
    if not name:
        name = binding.get_name()

    # if the parent doesn't have an empty name
    parent_name = binding.get_parent().get_name()
    if parent_name:
        name = f'{parent_name}/{name}'
        return _get_binding_path(binding.get_parent(), name)
    return name

def get_keyframes_from_channel(channel: Any) -> List[Tuple[int, float]]:
    """
    Get the keyframes from the given channel.

    Args:
        channel (Any): A channel in a level sequence.

    Returns:
        List[Tuple[int, float]]: A list of keyframes with their frame number and value.
    """
    keys = []
    for key in channel.get_keys():
        keys.append(
            (key.get_time().frame_number.value, key.get_value())
        )
    return keys

def get_sequence_track_keyframes(
        asset_path: str, 
        binding_path: str
    ) -> Dict[str, Any]:
    """
    Gets the transformations of the given bone on the given frame.

    Args:
        asset_path (str): The project path to the asset.
        binding_path (str): The path to the binding.

    Returns:
        Dict[str, Any]: A dictionary of transformation values with their keyframes.
    """
    sequence = unreal.load_asset(asset_path)
    bindings = {_get_binding_path(binding): binding for binding in sequence.get_bindings()}
    binding = bindings.get(binding_path)
    if not binding:
        return {}
    
    track = binding.get_tracks()[0]
    section = track.get_sections()[0]

    data = {}
    for channel in section.get_all_channels():
        # get the keyed frames for this curve's transforms
        keyframes = get_keyframes_from_channel(channel)
        curve_name = '_'.join(channel.get_name().split('_')[:-1])

        if keyframes:
            data[curve_name] = keyframes

    return data


def create_level_sequence(content_folder: str, name: str) -> unreal.LevelSequence:
    """
    Create a new level sequence in the given content folder.

    Args:
        content_folder (str): The content folder where the level sequence will be created.
        name (str): The name of the level sequence.

    Returns:
        unreal.LevelSequence: The created level sequence.
    """
    parts = [part for part in content_folder.split('/')]
    return content_browser.create_asset(
        asset_path="/" + "/".join(parts) + "/" + name,
        asset_class=unreal.LevelSequence, # type: ignore
        asset_factory=unreal.LevelSequenceFactoryNew(),
        unique_name=True
    )


def add_asset_to_level_sequence(
        asset: unreal.Object, 
        level_sequence: unreal.LevelSequence, 
        label: str
    ):
    """
    Add the asset to the level sequence.

    Args:
        asset (unreal.Object): The asset to add to the level sequence.
        level_sequence (unreal.LevelSequence): The level sequence to add the asset's actor to.
        label (str): The label of the actor when added to the level.
    """
    level_sequence_subsystem = unreal.get_editor_subsystem(unreal.LevelSequenceEditorSubsystem)
    level_sequence_library = unreal.LevelSequenceEditorBlueprintLibrary()
    
    # Open the level sequence
    level_sequence_library.open_level_sequence(level_sequence)

    # Remove the actor from the level sequence if it already exists
    actor = level.get_asset_actor_by_label(label)
    if actor:
        for binding in level_sequence.get_bindings():
            if binding.get_name() == label:
                level_sequence_subsystem.remove_actors_from_binding([actor], binding) # type: ignore

    level.delete_asset_actor_with_label(label)

    # Spawn the asset in the level, then add it to the level sequence
    actor = level.spawn_asset_in_level(
        asset=asset,
        label=label,
        replace_existing=True
    )

    # add the actor to the level sequence if it doesn't already exist, otherwise replace it
    for binding in level_sequence.get_bindings():
        if binding.get_name() == label:
            level_sequence_subsystem.replace_binding_with_actors([actor], binding) # type: ignore
            break
    else:
        level_sequence_subsystem.add_actors([actor]) # type: ignore