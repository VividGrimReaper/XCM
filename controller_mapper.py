bl_info = {
    "name": "Xbox Controller Mapper",
    "author": "You",
    "version": (2, 0),
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

# === XInput Fallback (Windows only) ===
XINPUT_AVAILABLE = False
try:
    if bpy.app.version >= (5, 0, 0):
        # Future-proof: check for native input devices first
        try:
            _devices = list(bpy.context.window_manager.input_devices)
            if any("Xbox" in dev.name for dev in _devices):
                XINPUT_AVAILABLE = "native"
        except Exception:
            pass

    if not XINPUT_AVAILABLE:
        import ctypes, platform
        if platform.system() == "Windows":
            class XINPUT_GAMEPAD(ctypes.Structure):
                _fields_ = [
                    ("wButtons", ctypes.c_ushort),
                    ("bLeftTrigger", ctypes.c_byte),
                    ("bRightTrigger", ctypes.c_byte),
                    ("sThumbLX", ctypes.c_short),
                    ("sThumbLY", ctypes.c_short),
                    ("sThumbRX", ctypes.c_short),
                    ("sThumbRY", ctypes.c_short),
                ]

            class XINPUT_STATE(ctypes.Structure):
                _fields_ = [
                    ("dwPacketNumber", ctypes.c_uint32),
                    ("Gamepad", XINPUT_GAMEPAD)
                ]

            xinput = ctypes.WinDLL("XInput1_4.dll")
            xinput.XInputGetState.argtypes = [ctypes.c_uint, ctypes.POINTER(XINPUT_STATE)]
            xinput.XInputGetState.restype = ctypes.c_uint

            def get_xinput_state(user_index=0):
                state = XINPUT_STATE()
                if xinput.XInputGetState(user_index, ctypes.byref(state)) == 0:
                    return state
                return None

            XINPUT_AVAILABLE = True
        else:
            print("⚠️  XInput only supported on Windows in this build.")
except Exception as e:
    XINPUT_AVAILABLE = False


# === Combo Mapping ===
class ControllerComboMapping(PropertyGroup):
    name: StringProperty(name="Combo Name", default="")
    keys: CollectionProperty(type=StringProperty)
    operator: StringProperty(name="Operator ID", default="")
    args_json: StringProperty(name="Args (JSON)", default='{}')
    hold_time: FloatProperty(default=0.2, min=0.05, max=2.0)


# === Main Mapping ===
class ControllerMapping(PropertyGroup):
    code: StringProperty(name="Event Code", default="")
    operator: StringProperty(name="Operator ID", default="")
    args_json: StringProperty(name="Args (JSON)", default='{}')


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

    mappings: CollectionProperty(type=ControllerMapping)
    mapping_index: IntProperty()

    def draw(self, context):
        layout = self.layout

        if not XINPUT_AVAILABLE:
            box = layout.box()
            box.alert = True
            box.label(text="XInput not available", icon='ERROR')
            box.label(text="Windows only for raw controller access")
            box.operator("wm.open_url", text="Learn More").url = "https://docs.microsoft.com/en-us/windows/win32/xinput/"

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
            c.name, k1, k2, k3 = "Maya Pan", *([c.keys.add() for _ in range(3)])
            k1.value, k2.value, k3.value = "ABS_X", "ABS_Y", "BTN_SOUTH"
            c.operator, c.args_json, c.hold_time = "view3d.view_pan", '{"offset": [0, 50]}', 0.2

            c = prefs.combos.add()
            c.name, k1, k2, k3 = "Maya Orbit", *([c.keys.add() for _ in range(3)])
            k1.value, k2.value, k3.value = "ABS_X", "ABS_Y", "BTN_EAST"
            c.operator, c.args_json, c.hold_time = "view3d.view_rotate", '{}', 0.2

        elif prefs.preset == "unity":
            prefs.axis_sensitivity = 1.2
            prefs.deadzone = 0.15

            for axis in [("ABS_X", "move X"), ("ABS_Y", "move Y")]:
                c = prefs.combos.add()
                c.name, k = f"Unity {axis[1]}", c.keys.add()
                k.value, c.operator, c.hold_time = axis[0], "view3d.view_pan", 0.0

        return {'FINISHED'}


# === Input Polling (XInput or fallback) ===
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

        # Poll XInput state (Windows only)
        try:
            if XINPUT_AVAILABLE and isinstance(XINPUT_AVAILABLE, bool):
                state = get_xinput_state()
                if state:
                    gp = state.Gamepad
                    events = []

                    # Buttons
                    btns = [
                        ("BTN_SOUTH", 0x0001), ("BTN_EAST", 0x0002),
                        ("BTN_NORTH", 0x0010), ("BTN_WEST", 0x0008)
                    ]
                    for code, mask in btns:
                        state = (gp.wButtons & mask) != 0
                        events.append(type('obj', (object,), {'code': code, 'state': int(state)})())

                    # Sticks
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

            else:  # Fallback
                return {'PASS_THROUGH'}

        except Exception as e:
            self.report({'WARNING'}, f"Controller error: {e}")
            prefs.enable_controller = False
            self._active = False
            return {'FINISHED'}

        now = bpy.context.scene.frame_current / bpy.context.scene.render.fps if hasattr(bpy.context.scene, "frame_current") else 0.0

        # Update pressed keys
        for evt in events:
            code = evt.code
            if evt.state == 1:  # Pressed (for buttons)
                self.pressed_keys.add(code)
            elif "ABS" in code:
                # Analog keys always "pressed" when active
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
            import json
            args = json.loads(combo.args_json) if combo.args_json else {}
        except Exception as e:
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

        try:
            get_xinput_state()  # test connection
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
