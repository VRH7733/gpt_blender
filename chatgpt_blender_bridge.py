# ✅ ChatGPT-Blender Bridge 
import pyperclip
import bpy
import os
import threading
import datetime
import json

#CHECKPOINTS_DIR = os.path.join(bpy.app.tempdir, "chatgpt_checkpoints")
_checkpoint_queue = []  # paths waiting to be saved (non-blocking)

# === File Paths ===
FOLDER = r"C:\Users\master\Desktop\chatgpt_blender_bridge"
INPUT_FILE = os.path.join(FOLDER, "input.txt")
OUTPUT_FILE = os.path.join(FOLDER, "output.txt")
SCENE_JSON_FILE = os.path.join(FOLDER, "scene_data.json")
RUN_SIGNAL_FILE = os.path.join(FOLDER, "run_now.txt")
TASK_MEMORY_FILE = os.path.join(FOLDER, "task_memory.json")
SELECTED_JSON_FILE = os.path.join(FOLDER, "selected.json") 
MACROS_DIR = os.path.join(FOLDER, "macros")
QUEUE_FILE = os.path.join(FOLDER, "queue.txt")
CONTROL_FILE = os.path.join(FOLDER, "control.txt")
CHECKPOINTS_DIR = os.path.join(FOLDER, "checkpoints")
checkpoint_counter = 0
# Selection poll (keeps selected.json fresh even without depsgraph events)
_SELECTION_POLL_SEC = 0.25

_macro_recording = False
_macro_buffer = []

_last_command = ""
_bridge_running = False
_bridge_timer = None

# === Log Task to Memory ===
def log_task_to_memory(command_text, scene_snapshot):
    try:
        memory_data = []
        if os.path.exists(TASK_MEMORY_FILE):
            with open(TASK_MEMORY_FILE, "r", encoding="utf-8") as f:
                memory_data = json.load(f)

        timestamp = datetime.datetime.now().isoformat()

        memory_data.append({
            "timestamp": timestamp,
            "command": command_text,
            "scene": scene_snapshot
        })

        with open(TASK_MEMORY_FILE, "w", encoding="utf-8") as f:
            json.dump(memory_data, f, indent=4)

    except Exception as e:
        print(f"⚠️ Failed to log task: {e}")


# === Export Scene Info (TXT) ===
def export_scene_info():
    try:
        lines = []
        lines.append("=== 🧠 Blender Project Context ===\n")

        lines.append("## 🧱 Scene Objects:")
        for obj in bpy.context.scene.objects:
            loc = f"[{round(obj.location.x, 3)}, {round(obj.location.y, 3)}, {round(obj.location.z, 3)}]"
            lines.append(f"- {obj.name} ({obj.type}) at {loc}")

        lines.append("\n## 🎨 Materials:")
        for mat in bpy.data.materials:
            lines.append(f"- {mat.name}")

        lines.append("\n## 📷 Cameras:")
        for obj in bpy.context.scene.objects:
            if obj.type == 'CAMERA':
                lines.append(f"- {obj.name}")

        lines.append("\n## 💡 Lights:")
        for obj in bpy.context.scene.objects:
            if obj.type == 'LIGHT':
                lines.append(f"- {obj.name} ({obj.data.type})")

        lines.append("\n## 🗂️ Collections:")
        for col in bpy.data.collections:
            lines.append(f"- {col.name} ({len(col.objects)} objects)")

        lines.append("\n## 🧩 Add-ons:")
        for addon in bpy.context.preferences.addons.keys():
            lines.append(f"- {addon}")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write("=== OUTPUT BEGIN ===\n")
            f.write("\n".join(lines))
            f.write("\n=== OUTPUT END ===")

    except Exception as e:
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            f.write(f"❌ Scene export error: {str(e)}")


# === Export Scene Info (JSON) ===
def export_scene_json():
    try:
        data = {
            "objects": [],
            "materials": [],
            "collections": [],
            "cameras": [],
            "lights": [],
            "addons": [],
        }

        for obj in bpy.context.scene.objects:
            obj_data = {
                "name": obj.name,
                "type": obj.type,
                "location": [round(c, 3) for c in obj.location],
                "modifiers": [m.name for m in obj.modifiers],
                "materials": [slot.material.name if slot.material else None for slot in obj.material_slots],
            }
            data["objects"].append(obj_data)

        for mat in bpy.data.materials:
            data["materials"].append(mat.name)

        for col in bpy.data.collections:
            data["collections"].append({
                "name": col.name,
                "object_count": len(col.objects)
            })

        for obj in bpy.context.scene.objects:
            if obj.type == 'CAMERA':
                data["cameras"].append(obj.name)

        for obj in bpy.context.scene.objects:
            if obj.type == 'LIGHT':
                data["lights"].append({
                    "name": obj.name,
                    "light_type": obj.data.type
                })

        for addon in bpy.context.preferences.addons.keys():
            data["addons"].append(addon)

        with open(SCENE_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)

    except Exception as e:
        print(f"❌ JSON export error: {e}")

def enqueue_checkpoint():
    """Compute a checkpoint path and queue it; actual save happens in checkpoint_poller()."""
    try:
        os.makedirs(CHECKPOINTS_DIR, exist_ok=True)
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        path = os.path.join(CHECKPOINTS_DIR, f"checkpoint_{stamp}.blend")
        _checkpoint_queue.append(path)
        print(f"🧷 Queued checkpoint → {path}")
        bpy.context.scene.chatgpt_last_checkpoint = path
    except Exception as e:
        print(f"⚠️ Failed to enqueue checkpoint: {e}")

def checkpoint_poller():
    """Runs on Blender's timer; saves at most one queued checkpoint per tick."""
    try:
        if _checkpoint_queue:
            path = _checkpoint_queue.pop(0)
            try:
                bpy.ops.wm.save_as_mainfile(filepath=path, copy=True)
                print(f"💾 Checkpoint saved → {path}")
            except Exception as e:
                print(f"❌ Checkpoint save failed: {e}")
        # run again soon; small interval keeps UI smooth
        return 0.5
    except Exception as e:
        print(f"⚠️ checkpoint_poller error: {e}")
        return 1.0

# === Run Code from input.txt ===
# === Run Code from input.txt ===
def run_chatgpt_command():
    global _last_command
    print("📨 Polling input.txt...")

    try:
        if not os.path.exists(INPUT_FILE):
            print("⚠️ input.txt not found")
            return

        with open(INPUT_FILE, "r", encoding="utf-8") as f:
            command = f.read().strip()

        if not command:
            print("ℹ️ input.txt is empty")
            return

        # Allow repeats (agent adds a unique runid comment)
        _last_command = command
        print("🔁 New command detected")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
            out.write("Running command...\n")

        def run_command_safe(code):
            def _run():
                try:
                    # Run the incoming code
                    exec(code, {"bpy": bpy})

                    # Animator: keyframe & advance (if enabled)
                    _animator_keyframe_and_advance()

                    # Safety Net: count + enqueue checkpoint if needed
                    scene = bpy.context.scene
                    scene.chatgpt_checkpoint_count += 1
                    freq = scene.chatgpt_checkpoint_freq
                    if freq > 0 and scene.chatgpt_checkpoint_count >= freq:
                        enqueue_checkpoint()
                        scene.chatgpt_checkpoint_count = 0

                    # Macro recording buffer
                    global _macro_recording, _macro_buffer
                    if _macro_recording:
                        _macro_buffer.append(code)

                    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
                        out.write("\n✅ Success\n")

                except Exception as e:
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
                        out.write(f"\n❌ Runtime Error: {str(e)}\n")

                # Always refresh context files
                export_scene_info()
                export_scene_json()

                try:
                    with open(SCENE_JSON_FILE, "r", encoding="utf-8") as f:
                        scene_snapshot = json.load(f)
                    log_task_to_memory(code, scene_snapshot)
                except Exception as e:
                    print(f"❌ Failed to load scene for task log: {e}")

                return None

            bpy.app.timers.register(_run)

        run_command_safe(command)

    except Exception as e:
        print(f"❌ Top-level bridge error: {str(e)}")


# === Timer Polling for run_now.txt ===
def poll():
    # If stopped, stop timer loop
    if not _bridge_running:
        print("🔕 Bridge paused; timer exiting.")
        return None

    if os.path.exists(RUN_SIGNAL_FILE):
        print("⏩ Run signal detected!")
        run_chatgpt_command()
        try:
            os.remove(RUN_SIGNAL_FILE)
            print("🧹 run_now.txt deleted")
        except Exception as e:
            print(f"⚠️ Couldn't delete run_now.txt: {e}")
    else:
        print("🔄 No run signal.")

    # Keep polling every 2 seconds
    return 2.0


class GPTQueueAdd(bpy.types.Operator):
    bl_idname = "wm.chatgpt_queue_add"
    bl_label = "Add Quick Command to Queue"
    def execute(self, context):
        try:
            cmd = context.scene.chatgpt_quick_command.strip()
            if not cmd:
                self.report({'WARNING'}, "Quick Command empty")
                return {'CANCELLED'}
            os.makedirs(MACROS_DIR, exist_ok=True)
            with open(QUEUE_FILE, "a", encoding="utf-8") as f:
                f.write(cmd.replace("\r\n", "\n").strip() + "\n")
            self.report({'INFO'}, "Queued 1 command")
            write_selection_snapshot()
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class GPTQueueClear(bpy.types.Operator):
    bl_idname = "wm.chatgpt_queue_clear"
    bl_label = "Clear Queue"
    def execute(self, context):
        try:
            open(QUEUE_FILE, "w", encoding="utf-8").close()
            self.report({'INFO'}, "Queue cleared")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class GPTMacroToggle(bpy.types.Operator):
    bl_idname = "wm.chatgpt_macro_toggle"
    bl_label = "Start/Stop Recording Macro"
    def execute(self, context):
        global _macro_recording, _macro_buffer
        _macro_recording = not _macro_recording
        if _macro_recording:
            _macro_buffer = []
            self.report({'INFO'}, "Macro recording: ON")
        else:
            self.report({'INFO'}, f"Macro recording: OFF ({len(_macro_buffer)} steps buffered)")
        return {'FINISHED'}

class GPTMacroSave(bpy.types.Operator):
    bl_idname = "wm.chatgpt_macro_save"
    bl_label = "Save Macro to File"
    def execute(self, context):
        try:
            os.makedirs(MACROS_DIR, exist_ok=True)
            ts = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(MACROS_DIR, f"macro_{ts}.jsonl")
            with open(path, "w", encoding="utf-8") as f:
                for step in _macro_buffer:
                    f.write(json.dumps({"code": step}) + "\n")
            self.report({'INFO'}, f"Saved macro ({len(_macro_buffer)} steps)")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

class GPTMacroPlay(bpy.types.Operator):
    bl_idname = "wm.chatgpt_macro_play"
    bl_label = "Play Last Macro"
    def execute(self, context):
        try:
            if not os.path.isdir(MACROS_DIR):
                self.report({'WARNING'}, "No macros folder yet")
                return {'CANCELLED'}
            files = [f for f in os.listdir(MACROS_DIR) if f.startswith("macro_") and f.endswith(".jsonl")]
            if not files:
                self.report({'WARNING'}, "No macro files found")
                return {'CANCELLED'}
            files.sort()  # by name timestamp
            latest = os.path.join(MACROS_DIR, files[-1])
            count = 0
            with open(latest, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        obj = json.loads(line)
                        code = obj.get("code", "").strip()
                        if code:
                            with open(QUEUE_FILE, "a", encoding="utf-8") as q:
                                q.write(code + "\n")
                            count += 1
                    except:
                        pass
            self.report({'INFO'}, f"Queued macro: {count} steps")
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, str(e))
            return {'CANCELLED'}

# Agent control buttons write to control.txt
def _write_control(cmd):
    with open(CONTROL_FILE, "w", encoding="utf-8") as f:
        f.write(cmd)

class GPTAgentPause(bpy.types.Operator):
    bl_idname = "wm.chatgpt_agent_pause"
    bl_label = "Pause Agent"
    def execute(self, context):
        _write_control("PAUSE")
        self.report({'INFO'}, "Agent PAUSE")
        return {'FINISHED'}

class GPTAgentResume(bpy.types.Operator):
    bl_idname = "wm.chatgpt_agent_resume"
    bl_label = "Resume Agent"
    def execute(self, context):
        _write_control("RESUME")
        self.report({'INFO'}, "Agent RESUME")
        return {'FINISHED'}

class GPTAgentStep(bpy.types.Operator):
    bl_idname = "wm.chatgpt_agent_step"
    bl_label = "Step Agent"
    def execute(self, context):
        _write_control("STEP")
        self.report({'INFO'}, "Agent STEP")
        return {'FINISHED'}

class GPTAgentStop(bpy.types.Operator):
    bl_idname = "wm.chatgpt_agent_stop"
    bl_label = "Stop Agent"
    def execute(self, context):
        _write_control("STOP")
        self.report({'INFO'}, "Agent STOP")
        return {'FINISHED'}


# === Blender UI Panel ===
class GPTBridgePanel(bpy.types.Panel):
    bl_label = "ChatGPT Bridge"
    bl_idname = "CHATGPT_PT_BRIDGE"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'ChatGPT'

    def draw(self, context):
        layout = self.layout

        # Bridge controls
        row = layout.row()
        row.operator("wm.chatgpt_bridge_toggle",
                     text=("Stop Bridge" if _bridge_running else "Start Bridge"),
                     icon='PLUGIN')
        layout.separator()
        layout.operator("wm.chatgpt_run_input", text="Run input.txt once", icon='PLAY')
        layout.prop(context.scene, "chatgpt_quick_command")
        layout.operator("wm.chatgpt_quick_send", text="Send Quick Command")
        layout.operator("wm.chatgpt_copy_scene_data", text="📤 Copy Scene JSON to Clipboard")

        # Focus
        layout.separator()
        layout.label(text="Focus Control")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_pin_focus", text="Pin Focus")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_pinned_name", text="Pinned Object")
        layout.operator("wm.chatgpt_pin_active", text="Pin Current Active")

        # Behavior (speed knobs)
        layout.separator()
        layout.label(text="Behavior")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_action_mode", text="")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_fast_mode")
        row.prop(context.scene, "chatgpt_delay_ms")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_burst_size")
        row.prop(context.scene, "chatgpt_confirm_every")

        # Animator
        layout.separator()
        layout.label(text="Animator Mode")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_animator_mode")
        row.prop(context.scene, "chatgpt_animator_step")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_anim_channels")

        # Safety Net Checkpoints
        layout.separator()
        layout.label(text="Safety Net Checkpoints")
        row = layout.row(align=True)
        row.prop(context.scene, "chatgpt_checkpoint_freq")
        layout.label(text=f"Last: {context.scene.chatgpt_last_checkpoint or 'None'}")
        layout.operator("chatgpt.revert_checkpoint", icon="FILE_REFRESH")

        # Queue & Macros
        layout.separator()
        layout.label(text="Queue & Macros")
        row = layout.row(align=True)
        row.operator("wm.chatgpt_queue_add", text="Queue Quick Cmd")
        row.operator("wm.chatgpt_queue_clear", text="Clear Queue")

        row = layout.row(align=True)
        row.operator("wm.chatgpt_macro_toggle", text="Start/Stop Record")
        row.operator("wm.chatgpt_macro_save", text="Save Macro")
        row.operator("wm.chatgpt_macro_play", text="Play Last Macro")

        # Agent Control
        row = layout.row(align=True)
        row.operator("wm.chatgpt_agent_pause", text="PAUSE")
        row.operator("wm.chatgpt_agent_resume", text="RESUME")
        row.operator("wm.chatgpt_agent_step", text="STEP")
        row.operator("wm.chatgpt_agent_stop", text="STOP")


class GPTBridgeRevertCheckpoint(bpy.types.Operator):
    bl_idname = "chatgpt.revert_checkpoint"
    bl_label = "Revert to Last Checkpoint"
    bl_description = "Reload the last saved checkpoint .blend file"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        path = context.scene.chatgpt_last_checkpoint
        if path and os.path.exists(path):
            bpy.ops.wm.open_mainfile(filepath=path)
            self.report({'INFO'}, f"Reverted to {path}")
            return {'FINISHED'}
        else:
            self.report({'WARNING'}, "No checkpoint file found")
            return {'CANCELLED'}



class GPTBridgeToggle(bpy.types.Operator):
    bl_idname = "wm.chatgpt_bridge_toggle"
    bl_label = "Toggle ChatGPT Bridge"

    def execute(self, context):
        global _bridge_running
        if _bridge_running:
            if _bridge_timer:
                _bridge_timer.cancel()
            _bridge_running = False
            self.report({'INFO'}, "Bridge stopped")
        else:
            bpy.app.timers.register(poll)
            _bridge_running = True
            self.report({'INFO'}, "Bridge started")
        return {'FINISHED'}


class GPTRunInputNow(bpy.types.Operator):
    bl_idname = "wm.chatgpt_run_input"
    bl_label = "Run input.txt manually"

    def execute(self, context):
        run_chatgpt_command()
        self.report({'INFO'}, "✅ input.txt executed once")
        return {'FINISHED'}


class GPTQuickSend(bpy.types.Operator):
    bl_idname = "wm.chatgpt_quick_send"
    bl_label = "Send Quick Command"

    def execute(self, context):
        command = context.scene.chatgpt_quick_command.strip()
        if command:
            with open(INPUT_FILE, "w", encoding="utf-8") as f:
                f.write(command)
            with open(RUN_SIGNAL_FILE, "w", encoding="utf-8") as f:
                f.write("run")
            self.report({'INFO'}, "📨 Command sent to input.txt")
        else:
            self.report({'WARNING'}, "⚠️ Quick command is empty")
        return {'FINISHED'}


class GPTCopySceneData(bpy.types.Operator):
    bl_idname = "wm.chatgpt_copy_scene_data"
    bl_label = "📤 Copy Scene JSON to Clipboard"

    def execute(self, context):
        try:
            with open(SCENE_JSON_FILE, "r", encoding="utf-8") as f:
                scene_json = f.read()
            pyperclip.copy(scene_json)
            self.report({'INFO'}, "Scene data copied to clipboard.")
        except Exception as e:
            self.report({'ERROR'}, f"Copy failed: {str(e)}")
        return {'FINISHED'}

class GPTPinActive(bpy.types.Operator):
    bl_idname = "wm.chatgpt_pin_active"
    bl_label = "Pin Current Active"

    def execute(self, context):
        active = context.view_layer.objects.active
        if active:
            context.scene.chatgpt_pinned_name = active.name
            context.scene.chatgpt_pin_focus = True
            self.report({'INFO'}, f"Pinned: {active.name}")
        else:
            self.report({'WARNING'}, "No active object to pin.")
        return {'FINISHED'}



def write_selection_snapshot():
    """Save active and selected object names for the agent."""
    try:
        # Active object (may be None)
        active = bpy.context.view_layer.objects.active
        active_name = active.name if active else None

        # Robust selected list (avoid context.selected_objects)
        selected_names = [o.name for o in bpy.context.view_layer.objects if o.select_get()]

        data = {
            "active": active_name,
            "selected": selected_names,
            "pinned": {
                "enabled": bool(bpy.context.scene.chatgpt_pin_focus),
                "name": bpy.context.scene.chatgpt_pinned_name or None,
            },
            "behavior": {
                "mode": bpy.context.scene.chatgpt_action_mode,
                "fast": bool(bpy.context.scene.chatgpt_fast_mode),
                "delay_ms": int(bpy.context.scene.chatgpt_delay_ms),
                "burst_size": int(bpy.context.scene.chatgpt_burst_size),          # ← add
                "confirm_every": int(bpy.context.scene.chatgpt_confirm_every),
                # ← add
                "animator": bool(getattr(bpy.context.scene, "chatgpt_animator_mode", False)),
                "anim_step": int(getattr(bpy.context.scene, "chatgpt_animator_step", 1)),
            }
        }


        with open(SELECTED_JSON_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️ Failed to write selected.json: {e}")

def _poll_selection_timer():
    """Lightweight periodic refresh of selected.json."""
    try:
        write_selection_snapshot()
    except Exception as e:
        print(f"⚠️ selection poll error: {e}")
    return _SELECTION_POLL_SEC  # re-run timer

# --- Pin Focus properties (add above register) ---
def _ensure_props():
    from bpy.props import BoolProperty, StringProperty
    if not hasattr(bpy.types.Scene, "chatgpt_pin_focus"):
        bpy.types.Scene.chatgpt_pin_focus = BoolProperty(
            name="Pin Focus",
            description="When enabled, the agent will prefer the pinned object name",
            default=False,
        )
    if not hasattr(bpy.types.Scene, "chatgpt_pinned_name"):
        bpy.types.Scene.chatgpt_pinned_name = StringProperty(
            name="Pinned Object",
            description="Name of the object to keep as focus",
            default="",
        )

def _animator_keyframe_and_advance():
    """If Animator Mode is ON: insert Loc/Rot/Scale keyframes for active+selected, then advance frame."""
    try:
        scn = bpy.context.scene
        if not getattr(scn, "chatgpt_animator_mode", False):
            return

        # Decide what to keyframe: active + all selected in the current view layer
        active = bpy.context.view_layer.objects.active
        selected = [o for o in bpy.context.view_layer.objects if o.select_get()]

        targets = set(selected)
        if active:
            targets.add(active)

        # Insert keyframes
        for obj in targets:
            try:
                obj.keyframe_insert(data_path="location")
                obj.keyframe_insert(data_path="rotation_euler")
                obj.keyframe_insert(data_path="scale")
            except Exception as e:
                print(f"⚠️ keyframe insert failed for {obj.name}: {e}")

        # Advance frame if step > 0
        step = int(getattr(scn, "chatgpt_animator_step", 1))
        if step > 0:
            scn.frame_set(scn.frame_current + step)

    except Exception as e:
        print(f"⚠️ animator error: {e}")

from bpy.app.handlers import persistent

@persistent
def on_depsgraph_update(scene):
    """Runs whenever the scene changes: keep all bridge files fresh."""
    try:
        export_scene_info()
        export_scene_json()
        write_selection_snapshot()
    except Exception as e:
        print(f"⚠️ depsgraph update failed: {e}")

def _ensure_props():
    from bpy.props import BoolProperty, StringProperty
    if not hasattr(bpy.types.Scene, "chatgpt_pin_focus"):
        bpy.types.Scene.chatgpt_pin_focus = BoolProperty(
            name="Pin Focus",
            description="Agent prefers this pinned object",
            default=False,
        )
    if not hasattr(bpy.types.Scene, "chatgpt_pinned_name"):
        bpy.types.Scene.chatgpt_pinned_name = StringProperty(
            name="Pinned Object",
            description="Name of the object to pin",
            default="",
        )

# --- Behavior props (mode & step sizes) ---
def _ensure_behavior_props():
    from bpy.props import EnumProperty, FloatProperty, BoolProperty, IntProperty

    if not hasattr(bpy.types.Scene, "chatgpt_action_mode"):
        bpy.types.Scene.chatgpt_action_mode = EnumProperty(
            name="Action",
            description="What the agent should do each loop",
            items=[
                ('MOVE_Z',   "Move Z",   "Move object upward on Z"),
                ('ROTATE_X', "Rotate X", "Rotate object around X"),
                ('SCALE_UNI',"Scale",    "Uniform scale up"),
                ('NUDGE_X',  "Nudge X",  "Small X translation"),
            ],
            default='MOVE_Z',
        )

    if not hasattr(bpy.types.Scene, "chatgpt_step_move"):
        bpy.types.Scene.chatgpt_step_move = FloatProperty(
            name="Move Step",
            description="Distance per loop when moving",
            default=1.0, min=-100.0, max=100.0
        )

    if not hasattr(bpy.types.Scene, "chatgpt_step_rotate"):
        bpy.types.Scene.chatgpt_step_rotate = FloatProperty(
            name="Rotate Step (rad)",
            description="Radians per loop when rotating",
            default=0.1, min=-3.1416, max=3.1416
        )

    if not hasattr(bpy.types.Scene, "chatgpt_step_scale"):
        bpy.types.Scene.chatgpt_step_scale = FloatProperty(
            name="Scale Step",
            description="Uniform scale amount per loop",
            default=0.05, min=-10.0, max=10.0
        )

    if not hasattr(bpy.types.Scene, "chatgpt_step_nudge"):
        bpy.types.Scene.chatgpt_step_nudge = FloatProperty(
            name="Nudge Step",
            description="Nudge distance per loop on X",
            default=0.2, min=-100.0, max=100.0
        )

    if not hasattr(bpy.types.Scene, "chatgpt_fast_mode"):
        bpy.types.Scene.chatgpt_fast_mode = BoolProperty(
            name="Fast Mode",
            description="Agent uses tight loop and minimal waiting",
            default=True
        )

    if not hasattr(bpy.types.Scene, "chatgpt_delay_ms"):
        bpy.types.Scene.chatgpt_delay_ms = IntProperty(
            name="Loop Delay (ms)",
            description="Agent sleep between commands (fast mode may ignore)",
            default=500, min=0, max=10000
        )

    if not hasattr(bpy.types.Scene, "chatgpt_burst_size"):
        bpy.types.Scene.chatgpt_burst_size = IntProperty(
            name="Burst Size",
            description="How many queue commands to fire per tick",
            default=10, min=1, max=500
        )

    if not hasattr(bpy.types.Scene, "chatgpt_confirm_every"):
        bpy.types.Scene.chatgpt_confirm_every = IntProperty(
            name="Confirm Every",
            description="Wait for Blender confirmation after every N sends",
            default=3, min=1, max=100
        )

    if not hasattr(bpy.types.Scene, "chatgpt_checkpoint_freq"):
        bpy.types.Scene.chatgpt_checkpoint_freq = bpy.props.IntProperty(
            name="Checkpoint Every N Commands",
            description="How often to save a .blend backup",
            default=5, min=1, max=100
        )

    if not hasattr(bpy.types.Scene, "chatgpt_checkpoint_count"):
        bpy.types.Scene.chatgpt_checkpoint_count = bpy.props.IntProperty(
            name="Internal counter for checkpoints",
            description="Tracks how many commands have run since last checkpoint",
            default=0
        )

    if not hasattr(bpy.types.Scene, "chatgpt_last_checkpoint"):
        bpy.types.Scene.chatgpt_last_checkpoint = bpy.props.StringProperty(
            name="Last Checkpoint File",
            default=""
        )

# --- Animator props (toggle + frame step) ---
def _ensure_animator_props():
    from bpy.props import BoolProperty, IntProperty, EnumProperty

    if not hasattr(bpy.types.Scene, "chatgpt_animator_mode"):
        bpy.types.Scene.chatgpt_animator_mode = BoolProperty(
            name="Animator Mode",
            description="After each command, set keyframes and auto-advance the frame",
            default=False,
        )

    if not hasattr(bpy.types.Scene, "chatgpt_animator_step"):
        bpy.types.Scene.chatgpt_animator_step = IntProperty(
            name="Frame Step",
            description="Frames to advance after keyframing (when Animator Mode is ON)",
            default=1, min=0, max=120
        )

    if not hasattr(bpy.types.Scene, "chatgpt_anim_channels"):
        bpy.types.Scene.chatgpt_anim_channels = EnumProperty(
            name="Key Channels",
            description="Which transforms to keyframe",
            items=[
                ('LOC', "Location", "Keyframe only location"),
                ('LOCROT', "Loc+Rot", "Keyframe location & rotation"),
                ('LOCROTSCALE', "Loc+Rot+Scale", "Keyframe location, rotation & scale"),
            ],
            default='LOCROTSCALE'
        )



# === Register & Selection Listener ===
def register():
    os.makedirs(MACROS_DIR, exist_ok=True)
    _ensure_props()
    _ensure_behavior_props()
    _ensure_animator_props()

    bpy.utils.register_class(GPTBridgePanel)
    bpy.utils.register_class(GPTBridgeToggle)
    bpy.utils.register_class(GPTRunInputNow)
    bpy.utils.register_class(GPTQuickSend)
    bpy.utils.register_class(GPTCopySceneData)
    bpy.utils.register_class(GPTBridgeRevertCheckpoint)
    # start the non-blocking checkpoint timer
    bpy.app.timers.register(checkpoint_poller)
    bpy.utils.register_class(GPTPinActive)

    bpy.utils.register_class(GPTQueueAdd)
    bpy.utils.register_class(GPTQueueClear)
    bpy.utils.register_class(GPTMacroToggle)
    bpy.utils.register_class(GPTMacroSave)
    bpy.utils.register_class(GPTMacroPlay)
    bpy.utils.register_class(GPTAgentPause)
    bpy.utils.register_class(GPTAgentResume)
    bpy.utils.register_class(GPTAgentStep)
    bpy.utils.register_class(GPTAgentStop)

    bpy.types.Scene.chatgpt_quick_command = bpy.props.StringProperty(name="Quick Command")

    # keep your depsgraph handler that calls export_scene_info/export_scene_json/write_selection_snapshot
    if on_depsgraph_update not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(on_depsgraph_update)

    # initial write
    export_scene_info()
    export_scene_json()
    write_selection_snapshot()
    # start lightweight selection poll
    try:
        bpy.app.timers.register(_poll_selection_timer, persistent=True)
    except Exception as e:
        print(f"⚠️ failed to start selection poll: {e}")





def unregister():
    if on_depsgraph_update in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(on_depsgraph_update)

    for cls in (
        GPTBridgePanel, GPTBridgeToggle, GPTRunInputNow, GPTQuickSend, GPTCopySceneData,
        GPTQueueAdd, GPTQueueClear, GPTMacroToggle, GPTMacroSave, GPTMacroPlay,
        GPTAgentPause, GPTAgentResume, GPTAgentStep, GPTAgentStop, GPTBridgeRevertCheckpoint, GPTAgentStop, GPTBridgeRevertCheckpoint, GPTPinActive

    ):
        bpy.utils.unregister_class(cls)

    for prop in (
        "chatgpt_quick_command", "chatgpt_action_mode",
        "chatgpt_fast_mode", "chatgpt_delay_ms",
        "chatgpt_pin_focus", "chatgpt_pinned_name",
        "chatgpt_burst_size", "chatgpt_confirm_every",
        "chatgpt_animator_mode", "chatgpt_anim_step", "chatgpt_anim_channels",
        "chatgpt_checkpoint_freq", "chatgpt_checkpoint_count", "chatgpt_last_checkpoint",
         "chatgpt_animator_step"
    ):
        if hasattr(bpy.types.Scene, prop):
            delattr(bpy.types.Scene, prop)



if __name__ == "__main__":
    register()

