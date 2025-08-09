#C:\Users\master\Desktop\chatgpt_blender_bridge\blender_clipboard_bridge.py
import pyperclip
import os
import time

FOLDER = r"C:\Users\master\Desktop\chatgpt_blender_bridge"
INPUT_FILE = os.path.join(FOLDER, "input.txt")
OUTPUT_FILE = os.path.join(FOLDER, "output.txt")
RUN_SIGNAL_FILE = os.path.join(FOLDER, "run_now.txt")

print("🟢 Clipboard monitor started.")
last_clip = ""

def looks_like_code(text):
    keywords = ["bpy", "import", "class", "def ", "for ", "while ", "exec(", "bpy.ops.", "bpy.context"]
    return any(kw in text for kw in keywords) and len(text.strip()) > 5

def wrap_template(natural_text):
    if "cube" in natural_text.lower():
        return 'bpy.ops.mesh.primitive_cube_add(location=(0,0,0))'
    elif "sphere" in natural_text.lower():
        return 'bpy.ops.mesh.primitive_uv_sphere_add(location=(0,0,0))'
    elif "delete all" in natural_text.lower():
        return 'bpy.ops.object.select_all(action="SELECT")\nbpy.ops.object.delete()'
    else:
        return f'# ❌ Could not auto-convert: {natural_text}'

def auto_fix(code):
    # Fix 1: Missing bpy import
    if "bpy" in code and "import bpy" not in code:
        code = "import bpy\n" + code

    # Fix 2: Add safe context for object access
    if ".location" in code and "obj =" not in code:
        code = "obj = bpy.context.active_object\n" + code

    # Fix 3: Empty block
    if len(code.strip()) < 5:
        code = "# ⚠️ Code was too short or empty"

    return code

while True:
    try:
        current_clip = pyperclip.paste()

        if current_clip != last_clip:
            last_clip = current_clip

            if looks_like_code(current_clip):
                print("📋 Code detected.")
                command = auto_fix(current_clip)

            else:
                print("💬 Natural command detected.")
                command = wrap_template(current_clip)

            with open(INPUT_FILE, "w", encoding="utf-8") as f:
                f.write(command)

            with open(RUN_SIGNAL_FILE, "w", encoding="utf-8") as f:
                f.write("run")

            print("✅ Blender command sent:", command.split("\n")[0])

        time.sleep(1)

    except KeyboardInterrupt:
        print("🛑 Monitor stopped.")
        break
    except Exception as e:
        print(f"❌ Clipboard Error: {e}")
        time.sleep(1)
