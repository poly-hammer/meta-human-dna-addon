import unreal
from typing import Optional


def get_asset_actor_by_label(label: str) -> Optional[unreal.Actor]:
    """
    Gets the asset actor by the given label.

    Args:
        label (str): The label of the actor.
    """
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in actor_subsystem.get_all_level_actors(): # type: ignore
        if label == actor.get_actor_label():
            return actor

def delete_asset_actor_with_label(label: str):
    """
    Deletes the actor with the given label.

    Args:
        label (str): The label of the actor.
    """
    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)
    for actor in actor_subsystem.get_all_level_actors(): # type: ignore
        if label == actor.get_actor_label():
            actor_subsystem.destroy_actor(actor) # type: ignore

def spawn_asset_in_level(
        label: str,
        asset: unreal.Object,
        location: Optional[list] = None,    
        rotation: Optional[list] = None,
        scale: Optional[list] = None,
        replace_existing: bool = False
    ) -> unreal.Actor:
    """
    Spawns the asset in the level.

    Args:
        label (str): The label of the actor.
        
        asset (unreal.Object): The asset object to spawn.
        
        location (list): The world location in the level to spawn the actor.
        
        rotation (list): The world rotation in degrees in the level to spawn the actor.
        
        scale (list): The scale of the actor.

        replace_existing (bool, optional): If true, this will delete any existing actor with this 
            label before spawning it. Defaults to False.
    """
    if not location:
        location = [0.0, 0.0, 0.0]
    if not rotation:
        rotation = [0.0, 0.0, 0.0]
    if not scale:  
        scale = [1.0, 1.0, 1.0]

    actor_subsystem = unreal.get_editor_subsystem(unreal.EditorActorSubsystem)

    # if we want to replace the existing actor, delete it first
    if replace_existing:
        delete_asset_actor_with_label(label)

    # spawn the actor at the origin since this method does not support scale
    actor = actor_subsystem.spawn_actor_from_object( # type: ignore
        asset,
        location=unreal.Vector(0.0, 0.0, 0.0),
        transient=False
    )
    actor.set_actor_label(asset.get_name())

    # now make the transform changes, since this can do scale, rotation, and location
    actor.set_actor_transform(
        new_transform=unreal.Transform(
            location=unreal.Vector(x=location[0], y=location[1], z=location[2]),
            rotation=unreal.Rotator(roll=rotation[0], pitch=rotation[1], yaw=rotation[2]),
            scale=unreal.Vector(x=scale[0], y=scale[1], z=scale[2])
        ),
        sweep=False,
        teleport=True
    )

    return actor