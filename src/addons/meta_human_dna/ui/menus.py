import bpy


def dna_import_operator_menu_item(self, context):
    self.layout.operator('meta_human_dna.import_dna', text='Metahuman DNA (.dna)')


def add_dna_import_menu():
    try:
        bpy.types.TOPBAR_MT_file_import.remove(dna_import_operator_menu_item)
    finally:
        bpy.types.TOPBAR_MT_file_import.append(dna_import_operator_menu_item)


def remove_dna_import_menu():
    bpy.types.TOPBAR_MT_file_import.remove(dna_import_operator_menu_item)
