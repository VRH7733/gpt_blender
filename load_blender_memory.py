# ✅ Phase 6-compatible: load_blender_memory.py
import json
import os

FOLDER = r"C:\Users\master\Desktop\chatgpt_blender_bridge"
SCENE_FILE = os.path.join(FOLDER, "scene_data.json")
TASK_FILE = os.path.join(FOLDER, "task_memory.json")

def load_json(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"❌ Failed to load {file_path}: {e}")
        return {}

def print_scene_data(scene):
    print("📦 Scene Objects:")
    for obj in scene.get("objects", []):
        print(f"- {obj['name']} ({obj['type']}) at {obj['location']}")

    print("\n🎨 Materials:", scene.get("materials", []))
    print("\n📷 Cameras:", scene.get("cameras", []))
    print("\n💡 Lights:", [f"{l['name']} ({l['light_type']})" for l in scene.get("lights", [])])
    print("\n🗂️ Collections:", [f"{c['name']} ({c['object_count']} objects)" for c in scene.get("collections", [])])
    print("\n🧩 Add-ons:", scene.get("addons", []))

def print_task_memory(tasks):
    print("\n🧠 Task History:")
    for task in tasks[-5:]:  # Last 5 tasks
        cmd = task.get("command", "No command")
        ts = task.get("timestamp", "No timestamp")
        print(f"- {ts} → {cmd}")

        print("  Objects:")
        for obj in task.get("scene", {}).get("objects", []):
            print(f"    • {obj['name']} ({obj['type']}) at {obj['location']}")

if __name__ == "__main__":
    scene = load_json(SCENE_FILE)
    tasks = load_json(TASK_FILE)

    print("\n=== 🧠 Blender Project Context ===\n")
    print_scene_data(scene)
    print_task_memory(tasks if isinstance(tasks, list) else [])
