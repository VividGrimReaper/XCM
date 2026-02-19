# filename: controller_mapper.py
bl_info = {
    "name": "Xbox Controller Mapper",
    "author": "You",
    "version": (1, 0),
    "blender": (4, 1, 0),
    "location": "View3D > Sidebar > Controller Mapper",
    "category": "Input"
}

import bpy
from bpy.props import BoolProperty, FloatProperty, EnumProperty, StringProperty
from bpy.types import Panel, Operator, AddonPreferences
import inputs

# --- Mapping Configuration ---
DEFAULT_MAPPING = {
    "BTN_SOUTH": ("wm.context_toggle", {"data_path": "scene.cursor.location[2]"}),  # dummy example
    "ABS_Y": ("view3d.view_pan", {}),  # vertical axis → pan Y
    "ABS_X": ("view3d.view_rotate", {}),
}

class ControllerMapperPreferences(AddonPreferences):
    bl_idname = __name__

    enable_controller: BoolProperty(
        name="Enable Controller",
        default=False,
        description="Toggle controller input override"
    )

    axis_sensitivity: FloatProperty(
        name="Axis Sensitivity",
        default=1.0, min=0.1, max=5.0
    )
    
    deadzone: FloatProperty(
        name="Deadzone",
        default=0.15, min=0.0, max=0.9
    )

    def draw(self, context):
        layout = self.layout
        col = layout.column()
        col.prop(self, "enable_controller")
        col.prop(self, "axis_sensitivity")
        col.prop(self, "deadzone")


# --- Input Polling (Modal Operator) ---
class WM_OT_toggle_controller_mode(Operator):
    bl_idname = "wm.toggle_controller_mode"
    bl_label = "Toggle Controller Mode"
    bl_description = "Enable/disable Xbox controller input override"

    _timer = None
    _joystick = None

    def modal(self, context, event):
        prefs = context.preferences.addons[__name__].preferences
        
        if not prefs.enable_controller:
            return {'PASS_THROUGH'}

        # Poll joystick events (non-blocking)
        try:
            events = inputs.get_gamepad()
            for event in events:
                # Example: map A button to left-click
                if event.code == "BTN_SOUTH" and event.state == 1:
                    bpy.ops.view3d.select_mouse('INVOKE_DEFAULT', mouse_x=0, mouse_y=0, extend=False)
                
                # Analog stick → pan/rotate (simplified)
                elif event.code in ("ABS_Y", "ABS_X"):
                    val = event.state / 32767.0
                    if abs(val) > prefs.deadzone:
                        sens = prefs.axis_sensitivity * (abs(val) - prefs.deadzone) / (1 - prefs.deadzone)
                        if event.code == "ABS_Y":
                            bpy.ops.view3d.view_pan('INVOKE_DEFAULT', offset=(0, -val * 50 * sens))
                        elif event.code == "ABS_X":
                            bpy.ops.view3d.view_rotate('INVOKE_DEFAULT', mouse_x=0, mouse_y=0)
        except Exception as e:
            self.report({'WARNING'}, f"Controller error: {e}")
            prefs.enable_controller = False

        return {'PASS_THROUGH'}

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        if not prefs.enable_controller:
            # Start polling
            try:
                devices = inputs.get_gamepad()
                self._joystick = True  # placeholder — real init below
            except Exception as e:
                self.report({'ERROR'}, f"Controller not found: {e}")
                return {'CANCELLED'}
            
            wm = context.window_manager
            self._timer = wm.event_timer_add(0.016, window=context.window)  # ~60 Hz
            wm.modal_handler_add(self)
            return {'RUNNING_MODAL'}
        else:
            prefs.enable_controller = False
            return {'FINISHED'}


# --- UI Panel ---
class VIEW3D_PT_controller_mapper(Panel):
    bl_label = "Controller Mapper"
    bl_idname = "VIEW3D_PT_controller_mapper"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Controller'

    def draw(self, context):
        layout = self.layout
        prefs = context.preferences.addons[__name__].preferences
        
        # Toggle button
        row = layout.row(align=True)
        if prefs.enable_controller:
            row.operator("wm.toggle_controller_mode", text="Disable Controller", icon='CHECKBOX_HLT')
        else:
            row.operator("wm.toggle_controller_mode", text="Enable Controller", icon='CHECKBOX_DEHLT')

        # Settings
        box = layout.box()
        box.label(text="Tuning")
        box.prop(prefs, "axis_sensitivity")
        box.prop(prefs, "deadzone")

        # Mapping editor (simplified)
        box = layout.box()
        box.label(text="Button Mappings (WIP)")
        box.operator("wm.controller_map_editor", text="Open Mapping Editor")


class WM_OT_controller_map_editor(Operator):
    bl_idname = "wm.controller_map_editor"
    bl_label = "Edit Controller Mappings"
    
    def execute(self, context):
        self.report({'INFO'}, "Mapping editor UI coming soon — for now, edit DEFAULT_MAPPING in code.")
        return {'FINISHED'}


# --- Registration ---
classes = (
    ControllerMapperPreferences,
    WM_OT_toggle_controller_mode,
    VIEW3D_PT_controller_mapper,
    WM_OT_controller_map_editor,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register default keymap (optional fallback)
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new(
            "wm.toggle_controller_mode", 'F12', 'PRESS', ctrl=True, shift=True
        )

def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
