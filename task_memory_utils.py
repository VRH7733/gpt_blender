#C:\Users\master\Desktop\chatgpt_blender_bridge\task_memory_utils.py
import json
import os

FOLDER = r"C:\Users\master\Desktop\chatgpt_blender_bridge"
TASK_MEMORY_FILE = os.path.join(FOLDER, "task_memory.json")

def load_task_memory():
    try:
        with open(TASK_MEMORY_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            if content.startswith("["):
                # Regular JSON array
                return json.loads(content)
            else:
                # JSONL (one entry per line)
                return [json.loads(line) for line in content.splitlines()]
    except Exception as e:
        print(f"❌ Failed to load task memory: {e}")
        return []


def get_last_command():
    tasks = load_task_memory()
    if not tasks:
        return "No tasks found."
    return tasks[-1].get("command", "No command")


def get_last_scene_objects():
    tasks = load_task_memory()
    if not tasks:
        return "No scene data found."
    return tasks[-1].get("scene", {}).get("objects", [])

def compare_last_two_tasks():
    tasks = load_task_memory()
    if len(tasks) < 2:
        return "Not enough tasks to compare."

    prev_objects = tasks[-2].get("scene", {}).get("objects", [])
    curr_objects = tasks[-1].get("scene", {}).get("objects", [])

    diffs = []
    for curr in curr_objects:
        match = next((p for p in prev_objects if p["name"] == curr["name"]), None)
        if match:
            if curr["location"] != match["location"]:
                diffs.append(f"{curr['name']} moved from {match['location']} to {curr['location']}")
            if curr["type"] != match["type"]:
                diffs.append(f"{curr['name']} type changed from {match['type']} to {curr['type']}")
        else:
            diffs.append(f"New object: {curr['name']} ({curr['type']})")

    for prev in prev_objects:
        if not any(c["name"] == prev["name"] for c in curr_objects):
            diffs.append(f"Deleted object: {prev['name']} ({prev['type']})")

    return diffs if diffs else ["No changes detected"]

# === Test Block ===
if __name__ == "__main__":
    print("🧠 Last Command:")
    print(get_last_command())

    print("\n📦 Last Scene Objects:")
    for obj in get_last_scene_objects():
        print(f"- {obj['name']} | {obj['type']} | {obj['location']}")

    print("\n🔍 Scene Differences:")
    for change in compare_last_two_tasks():
        print("-", change)
