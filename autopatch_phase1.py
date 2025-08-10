# autopatch_phase1.py
import re, sys, os, time

ROOT = os.path.dirname(__file__)
BRIDGE = os.path.join(ROOT, "chatgpt_blender_bridge.py")
AGENT  = os.path.join(ROOT, "agent_loop.py")

def read(p): 
    with open(p,'r',encoding='utf-8') as f: return f.read()
def write(p,s): 
    with open(p,'w',encoding='utf-8') as f: f.write(s)

def patch_bridge(src):
    changed = False

    # 1) Replace inner _run() body with single-exec + animator + checkpoint + recorder
    _run_pat = re.compile(
        r"def run_chatgpt_command\(\):.*?def run_command_safe\(code\):\s+def _run\(\):(.+?)\n\s*bpy\.app\.timers\.register\(_run.*?\)\n\s*\n\s*run_command_safe\(command\)",
        re.S
    )
    if _run_pat.search(src):
        new_body = r'''
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

        _last_command = command
        print("🔁 New command detected")

        with open(OUTPUT_FILE, "w", encoding="utf-8") as out:
            out.write("Running command...\\n")

        def run_command_safe(code):
            def _run():
                try:
                    exec(code, {"bpy": bpy})
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
                        out.write("\\n✅ Success\\n")

                    _animator_keyframe_and_advance()

                    scene = bpy.context.scene
                    scene.chatgpt_checkpoint_count += 1
                    freq = scene.chatgpt_checkpoint_freq
                    if freq > 0 and scene.chatgpt_checkpoint_count >= freq:
                        enqueue_checkpoint()
                        scene.chatgpt_checkpoint_count = 0

                    global _macro_recording, _macro_buffer
                    if _macro_recording:
                        _macro_buffer.append(code)

                except Exception as e:
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as out:
                        out.write(f"\\n❌ Runtime Error: {str(e)}\\n")

                export_scene_info()
                export_scene_json()

                try:
                    with open(SCENE_JSON_FILE, "r", encoding="utf-8") as f:
                        scene_snapshot = json.load(f)
                    log_task_to_memory(code, scene_snapshot)
                except Exception as e:
                    print(f"❌ Failed to load scene for task log: {e}")

                return None
            bpy.app.timers.register(_run, persistent=True)

        run_command_safe(command)

    except Exception as e:
        print(f"❌ Top-level bridge error: {str(e)}")
'''
        src = _run_pat.sub(new_body, src)
        changed = True
    else:
        print("WARN: Could not find _run() block to replace — skipping 1)")

    # 2) Ensure checkpoint poller is persistent in register()
    src_new = re.sub(
        r"bpy\.app\.timers\.register\(checkpoint_poller\)",
        r"bpy.app.timers.register(checkpoint_poller, persistent=True)",
        src
    )
    changed |= (src_new != src); src = src_new

    # 3) Make sure GPTPinActive is registered/unregistered
    if "class GPTPinActive(bpy.types.Operator)" in src:
        if "bpy.utils.register_class(GPTPinActive)" not in src:
            src = src.replace(
                "bpy.utils.register_class(GPTBridgeRevertCheckpoint)",
                "bpy.utils.register_class(GPTBridgeRevertCheckpoint)\n    bpy.utils.register_class(GPTPinActive)"
            )
            changed = True
        if "GPTPinActive," not in src:
            src = src.replace(
                "GPTAgentPause, GPTAgentResume, GPTAgentStep, GPTAgentStop, GPTBridgeRevertCheckpoint",
                "GPTAgentPause, GPTAgentResume, GPTAgentStep, GPTAgentStop, GPTBridgeRevertCheckpoint, GPTPinActive"
            )
            changed = True

    # 4) Remove duplicate Animator UI footer block if present
    dup_block = re.compile(
        r"\n\s*layout\.separator\(\)\s*\n\s*layout\.label\(text=\"Animator\"\)\s*\n\s*row = layout\.row\(align=True\)\s*\n\s*row\.prop\(context\.scene, \"chatgpt_animator_mode\"\)\s*\n\s*row\.prop\(context\.scene, \"chatgpt_animator_step\"\)\s*\n",
        re.S
    )
    src_new = dup_block.sub("\n", src)
    changed |= (src_new != src); src = src_new

    # 5) Ensure selection poller is persistent
    src_new = re.sub(
        r"bpy\.app\.timers\.register\(_poll_selection_timer, persistent=True\)",
        r"bpy.app.timers.register(_poll_selection_timer, persistent=True)",
        src
    )
    changed |= (src_new != src); src = src_new

    return src, changed


def patch_agent(src):
    changed = False
    # a) micro-yield after RUN_FILE write
    pat = re.compile(r"def _write_input_and_trigger\(cmd\):(.*?)\n\}", re.S)
    if "_write_input_and_trigger" in src and "time.sleep(0.005)" not in src:
        src = src.replace(
            'def _write_input_and_trigger(cmd):\n    with open(INPUT_FILE, "w", encoding="utf-8") as f:\n        f.write(cmd)\n    with open(RUN_FILE, "w", encoding="utf-8") as f:\n        f.write("run")',
            'def _write_input_and_trigger(cmd):\n    with open(INPUT_FILE, "w", encoding="utf-8") as f:\n        f.write(cmd)\n    with open(RUN_FILE, "w", encoding="utf-8") as f:\n        f.write("run")\n    time.sleep(0.005)  # tiny yield for Blender timer'
        )
        changed = True

    # b) defaults for burst/confirm if missing/low
    if 'def _read_behavior()' in src:
        src = re.sub(
            r"burst_size = int\(beh\.get\(\"burst_size\", ?\d+\)\)",
            r"burst_size = int(beh.get(\"burst_size\", 10))",
            src
        )
        src = re.sub(
            r"confirm_every = int\(beh\.get\(\"confirm_every\", ?\d+\)\)",
            r"confirm_every = int(beh.get(\"confirm_every\", 3))",
            src
        )
        changed = True
    return src, changed


def main():
    ok = True
    if os.path.exists(BRIDGE):
        src = read(BRIDGE)
        new, changed = patch_bridge(src)
        if changed:
            write(BRIDGE, new); print("✔ Patched chatgpt_blender_bridge.py")
        else:
            print("ℹ No changes applied to chatgpt_blender_bridge.py")
    else:
        print("ERR: chatgpt_blender_bridge.py not found"); ok = False

    if os.path.exists(AGENT):
        src = read(AGENT)
        new, changed = patch_agent(src)
        if changed:
            write(AGENT, new); print("✔ Patched agent_loop.py")
        else:
            print("ℹ No changes applied to agent_loop.py")
    else:
        print("WARN: agent_loop.py not found (skipping)")

    if not ok: sys.exit(1)

if __name__ == "__main__":
    main()
