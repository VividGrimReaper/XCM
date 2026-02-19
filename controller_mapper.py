bl_info = {
    "name": "Xbox Controller Mapper",
    "author": "Blender User + AI Assistant",
    "version": (1, 0, 3),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Controller",
    "description": "Use Xbox controller with persistent, customizable mappings & fine-tuning",
    "category": "Input"
}

import bpy
import os
import json
import webbrowser
from pathlib import Path
from bpy.props import (
    BoolProperty,
    FloatProperty,
    EnumProperty,
    StringProperty,
    CollectionProperty
)
from bpy.types import Panel, Operator, AddonPreferences, PropertyGroup


# --- Utility: Paths ---
def get_presets_dir():
    return Path(bpy.utils.user_resource('CONFIG', path='controller_mapper')) / "presets"


def ensure_preset_dir():
    d = get_presets_dir()
    d.mkdir(parents=True, exist_ok=True)
    return d


# --- Preset Management System ---
class ControllerMapperPreset(PropertyGroup):
    name: StringProperty(name="Preset Name", default="My Mapping")
    btn_south_op: StringProperty(default="view3d.select_mouse")
    btn_east_op: StringProperty(default="wm.undo")
    btn_north_op: StringProperty(default="render.render")
    btn_west_op: StringProperty(default="wm.save_mainfile")


class WM_OT_controller_save_preset(Operator):
    bl_idname = "wm.controller_save_preset"
    bl_label = "Save Current Mappings as Preset"
    
    name: StringProperty(name="Preset Name", default="New Mapping")

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        preset_dir = ensure_preset_dir()
        
        # Build preset data from current preferences
        preset_data = {
            "version": 1,
            "btn_south_op": prefs.map_BTN_SOUTH_op,
            "btn_east_op": prefs.map_BTN_EAST_op,
            "btn_north_op": prefs.map_BTN_NORTH_op,
            "btn_west_op": prefs.map_BTN_WEST_op,
        }
        
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in (' ', '-', '_') else '_' for c in self.name).strip()
        filepath = preset_dir / f"{safe_name}.json"
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(preset_data, f, indent=2)

        self.report({'INFO'}, f"Preset saved: {filepath}")
        return {'FINISHED'}

    def invoke(self, context, event):
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class WM_OT_controller_load_preset(Operator):
    bl_idname = "wm.controller_load_preset"
    bl_label = "Load Preset"
    
    preset_name: EnumProperty(
        name="Preset",
        items=lambda self, ctx: [
            (p.stem, p.stem.replace('_', ' ').title(), "") 
            for p in get_presets_dir().glob("*.json") if p.exists()
        ] or [("(none)", "No presets found", "")]
    )

    def execute(self, context):
        preset_path = get_presets_dir() / f"{self.preset_name}.json"
        
        if not preset_path.exists():
            self.report({'ERROR'}, "Preset file missing!")
            return {'CANCELLED'}
            
        with open(preset_path) as f:
            data = json.load(f)
        
        prefs = context.preferences.addons[__name__].preferences
        # Apply loaded mappings to preferences (which auto-update UI)
        if 'btn_south_op' in data:
            prefs.map_BTN_SOUTH_op = data['btn_south_op']
        if 'btn_east_op' in data:
            prefs.map_BTN_EAST_op = data['btn_east_op']
        if 'btn_north_op' in data:
            prefs.map_BTN_NORTH_op = data['btn_north_op']
        if 'btn_west_op' in data:
            prefs.map_BTN_WEST_op = data['btn_west_op']

        self.report({'INFO'}, f"Preset loaded: {self.preset_name}")
        return {'FINISHED'}

    def invoke(self, context, event):
        # Ensure at least one item exists to avoid enum error
        if not list(get_presets_dir().glob("*.json")):
            self.report({'WARNING'}, "No presets found. Save one first!")
            return {'CANCELLED'}
        
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class WM_OT_controller_delete_preset(Operator):
    bl_idname = "wm.controller_delete_preset"
    bl_label = "Delete Preset"
    
    preset_name: EnumProperty(
        name="Preset",
        items=lambda self, ctx: [
            (p.stem, p.stem.replace('_', ' ').title(), "") 
            for p in get_presets_dir().glob("*.json") if p.exists()
        ] or [("(none)", "No presets to delete", "")]
    )

    def execute(self, context):
        preset_path = get_presets_dir() / f"{self.preset_name}.json"
        if preset_path.exists():
            preset_path.unlink()
            self.report({'INFO'}, f"Deleted preset: {self.preset_name}")
        else:
            self.report({'WARNING'}, "Preset not found.")
        return {'FINISHED'}

    def invoke(self, context, event):
        if not list(get_presets_dir().glob("*.json")):
            self.report({'WARNING'}, "No presets to delete!")
            return {'CANCELLED'}
        
        wm = context.window_manager
        return wm.invoke_props_dialog(self)


# --- Main Addon Preferences (with persistent mappings) ---
class ControllerMapperPreferences(AddonPreferences):
    bl_idname = __name__

    enable_controller: BoolProperty(
        name="Enable Controller",
        default=False,
        description="Toggle Xbox controller input override"
    )

    axis_sensitivity: FloatProperty(
        name="Axis Sensitivity", default=1.0, min=0.1, max=5.0
    )
    
    deadzone: FloatProperty(name="Deadzone", default=0.2, min=0.0, max=0.9)

    # Mappings stored *directly* in preferences (Blender auto-saves these!)
    map_BTN_SOUTH_op: EnumProperty(
        name="A Button",
        items=[
            ('view3d.select_mouse', 'Select', ''),
            ('wm.undo', 'Undo', ''),
            ('wm.redo', 'Redo', '')
        ],
        default='view3d.select_mouse'
    )
    
    map_BTN_EAST_op: EnumProperty(
        name="B Button",
        items=[
            ('wm.undo', 'Undo', ''),
            ('wm.redo', 'Redo', ''),
            ('view3d.select_box', 'Box Select', '')
        ],
        default='wm.undo'
    )

    map_BTN_NORTH_op: EnumProperty(
        name="Y Button",
        items=[
            ('render.render', 'Render Image', ''),
            ('wm.save_mainfile', 'Save', '')
        ],
        default='render.render'
    )
    
    map_BTN_WEST_op: EnumProperty(
        name="X Button",
        items=[
            ('wm.save_mainfile', 'Save', ''),
            ('render.render', 'Render Image', '')
        ],
        default='wm.save_mainfile'
    )

    def draw(self, context):
        layout = self.layout
        
        # Global toggle
        row = layout.row(align=True)
        if self.enable_controller:
            row.operator("wm.toggle_controller_mode", text="Disable Controller", icon='CHECKBOX_HLT')
        else:
            row.operator("wm.toggle_controller_mode", text="Enable Controller", icon='CHECKBOX_DEHLT')

        # Tuning
        box = layout.box()
        box.label(text="Tuning", icon='MODIFIER')
        box.prop(self, "axis_sensitivity")
        box.prop(self, "deadzone")

        # Preset management (NEW!)
        box = layout.box()
        row = box.row(align=True)
        row.label(text="Presets", icon='FILE_REFRESH')
        
        sub = row.row(align=True)
        sub.operator("wm.controller_save_preset", text="", icon='ADD')
        sub.operator("wm.controller_load_preset", text="", icon='LOAD_FACTORY')
        sub.operator("wm.controller_delete_preset", text="", icon='TRASH')

        # Mappings
        box = layout.box()
        box.label(text="Button Mappings", icon='MOUSE_LMB')
        col = box.column(align=True)
        
        row = col.row(align=True)
        row.label(text="A (South)")
        row.prop(self, "map_BTN_SOUTH_op", text="")
        
        row = col.row(align=True)
        row.label(text="B (East)")
        row.prop(self, "map_BTN_EAST_op", text="")
        
        row = col.row(align=True)
        row.label(text="Y (North)")
        row.prop(self, "map_BTN_NORTH_op", text="")
        
        row = col.row(align=True)
        row.label(text="X (West)")
        row.prop(self, "map_BTN_WEST_op", text="")

        # Docs link
        box = layout.box()
        box.operator("wm.open_controller_docs", icon='HELP')


# --- Core Modal Operator ---
class WM_OT_toggle_controller_mode(Operator):
    bl_idname = "wm.toggle_controller_mode"
    bl_label = "Toggle Controller Mode"

    _timer = None

    def modal(self, context, event):
        prefs = context.preferences.addons[__name__].preferences
        
        if not prefs.enable_controller:
            return {'PASS_THROUGH'}

        try:
            import inputs
        except ImportError:
            self.report({'ERROR'}, "Missing 'inputs' library. Install with: pip install inputs")
            prefs.enable_controller = False
            return {'CANCELLED'}

        try:
            events = inputs.get_gamepad()
            for event in events:
                if hasattr(event, 'code') and hasattr(event, 'state'):
                    op_name = None

                    # Button mapping (uses live preferences)
                    if event.code == "BTN_SOUTH" and event.state == 1:
                        op_name = prefs.map_BTN_SOUTH_op
                    elif event.code == "BTN_EAST" and event.state == 1:
                        op_name = prefs.map_BTN_EAST_op
                    elif event.code == "BTN_NORTH" and event.state == 1:
                        op_name = prefs.map_BTN_NORTH_op
                    elif event.code == "BTN_WEST" and event.state == 1:
                        op_name = prefs.map_BTN_WEST_op

                    if op_name:
                        try:
                            op_module, op_id = op_name.split('.')
                            getattr(getattr(bpy.ops, op_module), op_id)('INVOKE_DEFAULT')
                        except Exception as e:
                            self.report({'WARNING'}, f"Operator '{op_name}' failed: {e}")

                    # Analog stick handling
                    elif event.code in ("ABS_Y", "ABS_X"):
                        val = event.state / 32767.0
                        if abs(val) > prefs.deadzone:
                            sens = prefs.axis_sensitivity * (abs(val) - prefs.deadzone) / (1 - prefs.deadzone)
                            if event.code == "ABS_Y":
                                bpy.ops.view3d.view_pan('INVOKE_DEFAULT', offset=(0, val * 40 * sens))
                            elif event.code == "ABS_X":
                                bpy.ops.view3d.view_rotate('INVOKE_DEFAULT', mouse_x=0, mouse_y=0)

        except Exception as e:
            self.report({'WARNING'}, f"Controller error: {e}")
            prefs.enable_controller = False

        return {'PASS_THROUGH'}

    def execute(self, context):
        import inputs
        if not hasattr(inputs, 'get_gamepad'):
            try:
                import inputs as _inputs
                globals()['inputs'] = _inputs
            except ImportError:
                self.report({'ERROR'}, "Missing 'inputs' library")
                return {'CANCELLED'}
        
        prefs = context.preferences.addons[__name__].preferences

        if not prefs.enable_controller:
            try:
                devices = inputs.get_gamepad()
                if not devices:
                    self.report({'WARNING'}, "No controller found.")
                    return {'CANCELLED'}
            except Exception as e:
                self.report({'ERROR'}, f"Failed to detect controller: {e}")
                return {'CANCELLED'}

            wm = context.window_manager
            self._timer = wm.event_timer_add(0.016, window=context.window)
            wm.modal_handler_add(self)
            prefs.enable_controller = True
            return {'RUNNING_MODAL'}
        else:
            prefs.enable_controller = False
            return {'FINISHED'}


class WM_OT_open_controller_docs(Operator):
    bl_idname = "wm.open_controller_docs"
    bl_label = "Open Documentation"

    def execute(self, context):
        addon_dir = Path(__file__).parent
        readme_path = addon_dir / "README.md"
        if readme_path.exists():
            webbrowser.open(f"file://{readme_path}")
        else:
            self.report({'WARNING'}, "README.md not found!")
        return {'FINISHED'}


class VIEW3D_PT_controller_mapper(Panel):
    bl_label = "Controller Mapper"
    bl_idname = "VIEW3D_PT_controller_mapper"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Controller'

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__name__].preferences
        
        row = layout.row(align=True)
        if prefs.enable_controller:
            row.operator("wm.toggle_controller_mode", text="Disable Controller", icon='CHECKBOX_HLT')
        else:
            row.operator("wm.toggle_controller_mode", text="Enable Controller", icon='CHECKBOX_DEHLT')


classes = (
    ControllerMapperPreferences,
    WM_OT_toggle_controller_mode,
    VIEW3D_PT_controller_mapper,
    WM_OT_open_controller_docs,
    WM_OT_controller_save_preset,
    WM_OT_controller_load_preset,
    WM_OT_controller_delete_preset,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
