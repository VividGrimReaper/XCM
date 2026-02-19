bl_info = {
    "name": "Xbox Controller Mapper",
    "author": "You",
    "version": (2, 2),
    "blender": (5, 0, 0),
    "location": "View3D > Sidebar > Controller Mapper",
    "category": "Input"
}

import bpy
from bpy.props import (
    BoolProperty, FloatProperty, EnumProperty,
    StringProperty, CollectionProperty, IntProperty
)
from bpy.types import Panel, Operator, AddonPreferences, PropertyGroup

# === XInput (Windows only) ===
XINPUT_AVAILABLE = False
try:
    import ctypes
    from ctypes import wintypes

    class XINPUT_GAMEPAD(ctypes.Structure):
        _fields_ = [
            ("wButtons", wintypes.WORD),
            ("bLeftTrigger", wintypes.BYTE),
            ("bRightTrigger", wintypes.BYTE),
            ("sThumbLX", wintypes.SHORT),
            ("sThumbLY", wintypes.SHORT),
            ("sThumbRX", wintypes.SHORT),
            ("sThumbRY", wintypes.SHORT),
        ]

    class XINPUT_STATE(ctypes.Structure):
        _fields_ = [
            ("dwPacketNumber", wintypes.DWORD),
            ("Gamepad", XINPUT_GAMEPAD)
        ]

    # Try multiple DLL names (some systems use 9.1.0, some 4.0)
    dll_names = ["XInput1_4.dll", "XInput9_1_0.dll"]
    xinput = None
    for name in dll_names:
        try:
            xinput = ctypes.WinDLL(name)
            break
        except OSError:
            continue

    if xinput:
        xinput.XInputGetState.argtypes = [ctypes.c_uint, ctypes.POINTER(XINPUT_STATE)]
        xinput.XInputGetState.restype = wintypes.DWORD

        def get_xinput_state(user_index=0):
            state = XINPUT_STATE()
            result = xinput.XInputGetState(user_index, ctypes.byref(state))
            return state if result == 0 else None

        XINPUT_AVAILABLE = True
    else:
        print("⚠️  XInput DLL not found (tried:", ", ".join(dll_names), ")")

except Exception as e:
    print(f"❌ XInput initialization failed: {e}")


# === Property Groups ===
class ControllerKey(PropertyGroup):
    value: StringProperty(name="Key", default="")


class ControllerComboMapping(PropertyGroup):
    name: StringProperty(default="")
    keys: CollectionProperty(type=ControllerKey)
    operator: StringProperty(default="")
    args_json: StringProperty(default='{}')
    hold_time: FloatProperty(default=0.2, min=0.05, max=2.0)


class ControllerMapping(PropertyGroup):
    code: StringProperty(default="")
    operator: StringProperty(default="")
    args_json: StringProperty(default='{}')


class ControllerMapperPreferences(AddonPreferences):
    bl_idname = __name__

    enable_controller: BoolProperty(default=False)
    show_preview: BoolProperty(default=True)

    axis_sensitivity: FloatProperty(default=1.0, min=0.1, max=5.0)
    deadzone: FloatProperty(default=0.15, min=0.0, max=0.9)

    preset: EnumProperty(
        name="Preset",
        items=[
            ("custom", "Custom", "", 0),
            ("maya", "Maya Navigation", "", 1),
            ("unity", "Unity Camera", "", 3),
        ],
        default="custom"
    )

    combos: CollectionProperty(type=ControllerComboMapping)
    combo_index: IntProperty()

    def draw(self, context):
        layout = self.layout

        if not XINPUT_AVAILABLE:
            box = layout.box()
            box.alert = True
            box.label(text="XInput initialization failed", icon='ERROR')
            box.label(text=f"Details: {', '.join(dll_names) if 'dll_names' in dir() else 'Unknown'}")
            box.operator("wm.open_url", text="Install XInput Drivers").url = "https://support.microsoft.com/en-us/windows/xbox-one-gamepad-drivers-6a2f7e5c-9b1d-4a8e-aa0a-3e3e3e3e3e3e"

        row = layout.row(align=True)
        row.prop(self, "preset", text="")
        if self.preset != "custom":
            row.operator("wm.controller_preset_apply", text="", icon='PLAY')

        col = layout.column(align=True)
        col.prop(self, "enable_controller")
        if XINPUT_AVAILABLE:
            col.prop(self, "axis_sensitivity")
            col.prop(self, "deadzone")

        box = layout.box()
        box.prop(self, "show_preview", icon='HIDE_OFF')


class WM_OT_controller_preset_apply(Operator):
    bl_idname = "wm.controller_preset_apply"
    bl_label = "Apply Preset"

    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences
        prefs.combos.clear()

        if prefs.preset == "maya":
            prefs.axis_sensitivity = 0.8
            prefs.deadzone = 0.12

            c = prefs.combos.add()
            c.name, k = "Maya Pan", [c.keys.add() for _ in range(3)]
            k[0].value, k[1].value, k[2].value = "ABS_X", "ABS_Y", "BTN_SOUTH"
            c.operator, c.args_json, c.hold_time = "view3d.view_pan", '{"offset": [0, 50]}', 0.2

            c = prefs.combos.add()
            c.name, k = "Maya Orbit", [c.keys.add() for _ in range(3)]
            k[0].value, k[1].value, k[2].value = "ABS_X", "ABS_Y", "BTN_EAST"
            c.operator, c.args_json, c.hold_time = "view3d.view_rotate", '{}', 0.2

        elif prefs.preset == "unity":
            prefs.axis_sensitivity = 1.2
            prefs.deadzone = 0.15

            for code in ["ABS_X", "ABS_Y"]:
                c = prefs.combos.add()
                k = c.keys.add()
                k.value, c.operator, c.hold_time = code, "view3d.view_pan", 0.0

        return {'FINISHED'}


class WM_OT_toggle_controller_mode(Operator):
    bl_idname = "wm.toggle_controller_mode"
    bl_label = "Toggle Controller Mode"

    _timer = None
    _active = False
    pressed_keys: set()
    combo_start_times: dict

    def modal(self, context, event):
        prefs = context.preferences.addons[__name__].preferences

        if not self._active:
            return {'PASS_THROUGH'}

        try:
            if XINPUT_AVAILABLE and (state := get_xinput_state()):
                gp = state.Gamepad
                events = []

                # Buttons
                btns = [
                    ("BTN_SOUTH", 0x0001), ("BTN_EAST", 0x0002),
                    ("BTN_NORTH", 0x0010), ("BTN_WEST", 0x0008)
                ]
                for code, mask in btns:
                    pressed = (gp.wButtons & mask) != 0
                    events.append(type('obj', (object,), {'code': code, 'state': int(pressed)})())

                # Analog sticks (deadzone-aware)
                deadzone = prefs.deadzone * 32767
                for code, val in [
                    ("ABS_X", gp.sThumbLX), ("ABS_Y", -gp.sThumbLY),
                    ("ABS_RX", gp.sThumbRX), ("ABS_RY", -gp.sThumbRY)
                ]:
                    if abs(val) > deadzone:
                        events.append(type('obj', (object,), {
                            'code': code,
                            'state': int(val * 32767 / 32768)
                        })())

            else:  # No controller connected or XInput not working
                return {'PASS_THROUGH'}

        except Exception as e:
            self.report({'WARNING'}, f"Controller error: {e}")
            prefs.enable_controller = False
            self._active = False
            return {'FINISHED'}

        now = bpy.context.scene.frame_current / bpy.context.scene.render.fps if hasattr(bpy.context.scene, "frame_current") else 0.0

        # Update pressed keys state
        for evt in events:
            code = evt.code
            if evt.state == 1:  # Button press
                self.pressed_keys.add(code)
            elif "ABS" in code:
                self.pressed_keys.add(code)

        # Check combos
        for i, combo in enumerate(prefs.combos):
            combo_keys = {k.value for k in combo.keys}
            if combo_keys.issubset(self.pressed_keys):
                if i not in self.combo_start_times:
                    self.combo_start_times[i] = now
            else:
                self.combo_start_times.pop(i, None)

        # Execute combos past hold time
        for i, combo in enumerate(prefs.combos):
            start_time = self.combo_start_times.get(i)
            if start_time is not None and (now - start_time) >= combo.hold_time:
                self._execute_combo(context, combo, now)

        return {'PASS_THROUGH'}

    def _execute_combo(self, context, combo, now):
        idx = next((k for k, v in self.combo_start_times.items() if v == now - combo.hold_time), None)
        if idx is not None:
            del self.combo_start_times[idx]

        try:
            args = __import__('json').loads(combo.args_json) if combo.args_json else {}
        except Exception:
            return

        try:
            op_name, space_type = combo.operator.split(".", 1)
            getattr(getattr(bpy.ops, op_name), space_type)(**args)
        except Exception:
            pass


    def execute(self, context):
        prefs = context.preferences.addons[__name__].preferences

        if not XINPUT_AVAILABLE:
            self.report({'ERROR'}, "XInput not available (Windows only)")
            return {'CANCELLED'}

        if prefs.enable_controller:
            prefs.enable_controller = False
            self._active = False
            self.pressed_keys.clear()
            self.combo_start_times.clear()
            return {'FINISHED'}

        bpy.ops.wm.controller_preset_apply()

        # Test controller connection
        try:
            if not get_xinput_state():
                self.report({'WARNING'}, "Controller found but disconnected or unresponsive.")
        except Exception as e:
            self.report({'ERROR'}, f"Controller not found: {e}")
            return {'CANCELLED'}

        prefs.enable_controller = True
        self._active = True

        wm = context.window_manager
        self._timer = wm.event_timer_add(0.016, window=context.window)
        wm.modal_handler_add(self)

        return {'RUNNING_MODAL'}


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
        row.prop(prefs, "preset", text="")
        if prefs.preset != "custom":
            row.operator("wm.controller_preset_apply", text="Apply")

        row = layout.row(align=True)
        icon = 'CHECKBOX_HLT' if prefs.enable_controller else 'CHECKBOX_DEHLT'
        row.operator(
            "wm.toggle_controller_mode",
            text="Disable Controller" if prefs.enable_controller else "Enable Controller",
            icon=icon
        )

        box = layout.box()
        box.label(text="Tuning")
        if XINPUT_AVAILABLE:
            box.prop(prefs, "axis_sensitivity")
            box.prop(prefs, "deadzone")

        row = layout.row(align=True)
        row.prop(prefs, "show_preview", icon='HIDE_OFF')


classes = (
    ControllerKey,
    ControllerComboMapping,
    ControllerMapping,
    ControllerMapperPreferences,
    VIEW3D_PT_controller_mapper,
    WM_OT_toggle_controller_mode,
    WM_OT_controller_preset_apply,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)

    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps.new(name='3D View', space_type='VIEW_3D')
        kmi = km.keymap_items.new("wm.toggle_controller_mode", 'F12', 'PRESS', ctrl=True, shift=True)


def unregister():
    wm = bpy.context.window_manager
    kc = wm.keyconfigs.addon
    if kc:
        km = kc.keymaps['3D View']
        for kmi in km.keymap_items:
            if kmi.idname == "wm.toggle_controller_mode":
                km.keymap_items.remove(kmi)
                break

    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()
