from meta_human_dna.ui.callbacks import get_active_rig_logic
from typing import Any

def set_body_pose(
        solver_name: str, 
        pose_name: str
    ) -> tuple[Any, int, int]:
    instance = get_active_rig_logic()
    if instance:
        instance.editing_rbf_solver = True
        instance.auto_evaluate_body = False
        for solver_index, solver in enumerate(instance.rbf_solver_list): # type: ignore
            if solver.name == solver_name:
                instance.rbf_solver_list_active_index = solver_index # type: ignore
                for pose_index, pose in enumerate(solver.poses): # type: ignore
                    if pose.name == pose_name:
                        solver.poses_active_index = pose_index # type: ignore
                        return pose, solver_index, pose_index