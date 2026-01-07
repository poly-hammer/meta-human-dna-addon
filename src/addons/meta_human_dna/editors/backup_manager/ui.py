import bpy

def get_active_rig_instance():
    # Avoid circular import
    from ...ui.callbacks import get_active_rig_instance as _get_active_rig_instance
    return _get_active_rig_instance()

class META_HUMAN_DNA_UL_dna_backups(bpy.types.UIList):
    """UIList for displaying DNA backup entries."""
    
    def draw_item(
        self,
        context,
        layout,
        data,
        item,
        icon,
        active_data,
        active_propname
    ):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            # Timestamp
            row.label(text=item.timestamp, icon='TIME')
            # Description
            row.label(text=item.description)
        elif self.layout_type == 'GRID':
            layout.alignment = 'CENTER'
            layout.label(text=item.timestamp, icon='TIME')


class META_HUMAN_DNA_PT_dna_backups(bpy.types.Panel):
    """Panel for displaying and managing DNA backups."""
    bl_label = "Backup Manager"
    bl_idname = "META_HUMAN_DNA_PT_dna_backups"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'MetaHuman DNA'
    bl_options = {'DEFAULT_CLOSED'}
    
    @classmethod
    def poll(cls, context):
        return get_active_rig_instance() is not None
    
    def draw(self, context):
        
        layout = self.layout
        if not layout:
            return
        
        instance = get_active_rig_instance()
        if instance is None:
            layout.label(text="No active MetaHuman instance", icon='INFO')
            return
        
        # Instance name header
        layout.label(text=f"Instance: {instance.name}", icon='ARMATURE_DATA')
        
        # Backup list
        row = layout.row()
        row.template_list(
            "META_HUMAN_DNA_UL_dna_backups",
            "dna_backup_list_id",
            instance,
            "dna_backup_list",
            instance,
            "dna_backup_list_active_index",
            rows=4 if len(instance.dna_backup_list) > 0 else 1 # type: ignore
        )
        
        # Side buttons
        col = row.column(align=True)
        col.operator("meta_human_dna.sync_dna_backups", text="", icon='FILE_REFRESH')
        col.operator("meta_human_dna.open_backup_folder", text="", icon='FILE_FOLDER')
        
        # Bottom buttons
        if len(instance.dna_backup_list) > 0: # type: ignore
            row = layout.row(align=True)
            row.operator("meta_human_dna.restore_dna_backup", text="Restore", icon='LOOP_BACK')
            row.operator("meta_human_dna.delete_dna_backup", text="Delete", icon='TRASH')
            
            # Show selected backup details
            active_index = instance.dna_backup_list_active_index # type: ignore
            if 0 <= active_index < len(instance.dna_backup_list): # type: ignore
                backup = instance.dna_backup_list[active_index] # type: ignore
                box = layout.box()
                box.label(text=f"Type: {backup.backup_type}", icon='INFO')
        else:
            layout.label(text="No backups available", icon='INFO')
