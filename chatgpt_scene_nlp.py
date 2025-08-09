# ✅ ChatGPT-Blender Scene NLP
import json
import os

FOLDER = r"C:\Users\master\Desktop\chatgpt_blender_bridge"
SCENE_JSON_FILE = os.path.join(FOLDER, "scene_data.json")
TASK_MEMORY_FILE = os.path.join(FOLDER, "task_memory.json")
SELECTED_JSON_FILE = os.path.join(FOLDER, "selected.json")

def load_scene():
    try:
        with open(SCENE_JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to load scene: {e}")
        return {}


def load_memory():
    try:
        with open(TASK_MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to load memory: {e}")
        return []


def summarize_scene(scene):
    print("\n📦 Scene Summary:")
    for obj in scene.get("objects", []):
        print(f"- {obj['name']} ({obj['type']}) at {obj['location']}")

    print("\n🎨 Materials:", scene.get("materials", []))
    print("\n📷 Cameras:", scene.get("cameras", []))
    print("\n💡 Lights:", [f"{l['name']} ({l['light_type']})" for l in scene.get("lights", [])])
    print("\n🗂️ Collections:", [f"{c['name']} ({c['object_count']} objects)" for c in scene.get("collections", [])])
    print("\n🧩 Addons:", scene.get("addons", []))


def ask_blender_ai():
    scene = load_scene()
    memory = load_memory()

    summarize_scene(scene)

    if memory:
        last = memory[-1]
        desc = last.get("command", "No last command found.")
        print("\n📝 Last command:", desc.strip())
    else:
        print("\n📭 No memory entries found.")

# --- Drop-in smarter generator (Phase 7.3) ---
def generate_command_from_memory():
    import random

    # Load scene / memory
    try:
        with open(SCENE_JSON_FILE, "r", encoding="utf-8") as f:
            scene = json.load(f)
    except Exception:
        scene = {}

    try:
        with open(TASK_MEMORY_FILE, "r", encoding="utf-8") as f:
            memory = json.load(f)
    except Exception:
        memory = []

    sel = load_selection()
    pinned = sel.get("pinned", {}) or {}
    pin_enabled = bool(pinned.get("enabled"))
    pin_name = pinned.get("name") or None
    active_name = sel.get("active")

    behavior = sel.get("behavior", {}) or {}
    mode = behavior.get("mode", "MOVE_Z")
    step_move = float(behavior.get("step_move", 1.0))
    step_rot  = float(behavior.get("step_rotate", 0.1))
    step_scl  = float(behavior.get("step_scale", 0.05))
    step_nud  = float(behavior.get("step_nudge", 0.2))

    objs = scene.get("objects", [])
    mesh_objs = [o for o in objs if o.get("type") == "MESH"]

    def last_location_from_memory(name):
        for task in reversed(memory):
            for o in task.get("scene", {}).get("objects", []):
                if o.get("name") == name:
                    return o.get("location")
        return None

    # Focus selection order
    focus = None
    if pin_enabled and pin_name:
        focus = next((o for o in objs if o.get("name") == pin_name), None)
    if focus is None and active_name:
        focus = next((o for o in objs if o.get("name") == active_name), None)
    if focus is None:
        focus = next((o for o in objs if o.get("name") == "Cube"), None)
    if focus is None and mesh_objs:
        focus = mesh_objs[0]
    if focus is None:
        return 'bpy.ops.mesh.primitive_cube_add(location=(0, 0, 0))  # Create Cube (no mesh in scene)'

    name = focus["name"]
    otype = focus.get("type", "MESH")
    loc   = focus.get("location", [0.0, 0.0, 0.0])

    # Non-mesh? Default to NUDGE_X behavior
    if otype in ("LIGHT", "CAMERA"):
        new_x = round(loc[0] + step_nud, 3)
        return (
            f'obj = bpy.data.objects["{name}"]\n'
            f'obj.location.x = {new_x}'
        )

    # Mesh behaviors
    if mode == "MOVE_Z":
        new_z = round(loc[2] + step_move, 3)
        return (
            f'obj = bpy.data.objects["{name}"]\n'
            f'obj.location.z = {new_z}'
        )
    elif mode == "ROTATE_X":
        # use += for rotation so we don’t need prior angle
        return (
            f'obj = bpy.data.objects["{name}"]\n'
            f'obj.rotation_euler.x += {step_rot}'
        )
    elif mode == "SCALE_UNI":
        # read last scale from memory if you logged it; otherwise add a small positive delta
        # for simplicity, just do a multiplicative bump using current location context
        return (
            f'obj = bpy.data.objects["{name}"]\n'
            f'obj.scale.x += {step_scl}\n'
            f'obj.scale.y += {step_scl}\n'
            f'obj.scale.z += {step_scl}'
        )
    elif mode == "NUDGE_X":
        new_x = round(loc[0] + step_nud, 3)
        return (
            f'obj = bpy.data.objects["{name}"]\n'
            f'obj.location.x = {new_x}'
        )
    else:
        # Fallback
        new_z = round(loc[2] + step_move, 3)
        return (
            f'obj = bpy.data.objects["{name}"]\n'
            f'obj.location.z = {new_z}'
        )

        
def load_selection():
    try:
        with open(SELECTED_JSON_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"active": None, "selected": []}


# === Run this to interact with the context ===
if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        mode = sys.argv[1]
        if mode == "summary":
            ask_blender_ai()
        elif mode == "plain":
            scene = load_scene()
            memory = load_memory()

            names = [obj['name'] for obj in scene.get("objects", [])]
            print(f"🧠 Blender has {len(names)} objects: {', '.join(names)}.")

            if memory:
                last = memory[-1]
                desc = last.get("command", "No command.")
                print(f"🧭 Last command: {desc.strip()}")
            else:
                print("📭 No previous command found.")
    else:
        ask_blender_ai()
