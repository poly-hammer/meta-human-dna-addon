# standard library imports
import logging

# local imports
from ... import utilities
from ...typing import *  # noqa: F403


logger = logging.getLogger(__name__)


def update_body_rbf_solver_list(self: "RigInstance"):  # noqa: PLR0912
    if not utilities.dependencies_are_valid():
        return

    import meta_human_dna_core

    # skip if the body rig is not set
    if not self.body_rig or not self.body_dna_reader:
        return

    last_active_solver_index = -1
    last_active_pose_index = -1
    last_active_driven_index = -1
    last_active_driver_index = -1

    # store the last active indices to try and preserve them after updating the list
    if len(self.rbf_solver_list) > 0:
        last_active_solver_index = self.rbf_solver_list_active_index
        _solver = self.rbf_solver_list[last_active_solver_index]
        if len(_solver.poses) > 0:
            last_active_pose_index = _solver.poses_active_index
            _pose = _solver.poses[last_active_pose_index]
            if len(_pose.driven) > 0:
                last_active_driven_index = _pose.driven_active_index
            if len(_pose.drivers) > 0:
                last_active_driver_index = _pose.drivers_active_index

    self.rbf_solver_list.clear()
    for solver_data in meta_human_dna_core.get_rbf_solver_data(self.body_dna_reader):
        solver = self.rbf_solver_list.add()
        for solver_field_name in solver_data.__annotations__:
            if solver_field_name == "poses":
                solver.poses.clear()
                for pose_data in solver_data.poses:
                    pose = solver.poses.add()
                    for pose_field_name in pose_data.__annotations__:
                        if pose_field_name == "driven":
                            pose.driven.clear()
                            for driven_data in pose_data.driven:
                                driven = pose.driven.add()
                                for driven_field_name in driven_data.__annotations__:
                                    setattr(driven, driven_field_name, getattr(driven_data, driven_field_name))
                        elif pose_field_name == "drivers":
                            pose.drivers.clear()
                            for driver_data in pose_data.drivers:
                                driver = pose.drivers.add()
                                for driver_field_name in driver_data.__annotations__:
                                    setattr(driver, driver_field_name, getattr(driver_data, driver_field_name))
                        else:
                            setattr(pose, pose_field_name, getattr(pose_data, pose_field_name))
            else:
                setattr(solver, solver_field_name, getattr(solver_data, solver_field_name))

    # restore the last active indices if possible
    if last_active_solver_index >= 0 and last_active_solver_index < len(self.rbf_solver_list):
        self.rbf_solver_list_active_index = last_active_solver_index
        _solver = self.rbf_solver_list[last_active_solver_index]
        if last_active_pose_index >= 0 and last_active_pose_index < len(_solver.poses):
            _solver.poses_active_index = last_active_pose_index
            _pose = _solver.poses[last_active_pose_index]
            if last_active_driven_index >= 0 and last_active_driven_index < len(_pose.driven):
                _pose.driven_active_index = last_active_driven_index
            if last_active_driver_index >= 0 and last_active_driver_index < len(_pose.drivers):
                _pose.drivers_active_index = last_active_driver_index
