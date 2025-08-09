# agent_loop.py — fast burst queue agent with richer NLP
import os, time, json, re

# ---------- paths ----------
FOLDER        = r"C:\Users\master\Desktop\chatgpt_blender_bridge"
INPUT_FILE    = os.path.join(FOLDER, "input.txt")
RUN_FILE      = os.path.join(FOLDER, "run_now.txt")
OUTPUT_FILE   = os.path.join(FOLDER, "output.txt")
SCENE_FILE    = os.path.join(FOLDER, "scene_data.json")
QUEUE_FILE    = os.path.join(FOLDER, "queue.txt")
CONTROL_FILE  = os.path.join(FOLDER, "control.txt")
SELECTED_FILE = os.path.join(FOLDER, "selected.json")

# ---------- tiny utils ----------
def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return default

def _read_text(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except:
        return ""

def _mtime(path):
    try:
        return os.path.getmtime(path)
    except:
        return 0

def _write_input_and_trigger(cmd):
    # add a unique run id so the bridge never ignores as "same command"
    unique = f"{cmd}\n# runid {time.time_ns()}"
    with open(INPUT_FILE, "w", encoding="utf-8") as f:
        f.write(unique)
    with open(RUN_FILE, "w", encoding="utf-8") as f:
        f.write("run")

def _wait_for_blender(prev_scene_mtime, timeout=6.0):
    """Wait until scene_data.json changes or '✅ Success' appears in output.txt."""
    start = time.time()
    while time.time() - start < timeout:
        if _mtime(SCENE_FILE) > prev_scene_mtime:
            return True
        if "✅ Success" in _read_text(OUTPUT_FILE):
            return True
        time.sleep(0.05)
    return False

def _read_behavior():
    """Read live speed knobs from selected.json → behavior section."""
    sel = _read_json(SELECTED_FILE, {})
    beh = sel.get("behavior", {})
    fast          = bool(beh.get("fast", True))
    delay_ms      = int(beh.get("delay_ms", 500))
    burst_size    = int(beh.get("burst_size", 5))
    confirm_every = int(beh.get("confirm_every", 1))
    if burst_size < 1: burst_size = 1
    if confirm_every < 1: confirm_every = 1
    return fast, max(0, delay_ms), burst_size, confirm_every

def _read_control():
    txt = _read_text(CONTROL_FILE).strip().upper()
    return txt if txt in ("", "PAUSE", "RESUME", "STOP", "STEP") else ""

def _pop_queue_block():
    """
    Return one 'paragraph' (list of lines) separated by a blank line.
    Leading blank lines are ignored. Remaining queue is written back.
    """
    try:
        if not os.path.exists(QUEUE_FILE):
            return None
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            lines = [ln.rstrip("\n") for ln in f.readlines()]

        # drop leading empties
        while lines and lines[0].strip() == "":
            lines.pop(0)
        if not lines:
            open(QUEUE_FILE, "w", encoding="utf-8").close()
            return None

        block = []
        while lines:
            ln = lines.pop(0)
            if ln.strip() == "":
                break
            block.append(ln)

        with open(QUEUE_FILE, "w", encoding="utf-8") as f:
            for ln in lines:
                f.write(ln + "\n")

        return block if block else None
    except Exception as e:
        print("Queue error:", e)
        return None

# ---------- NATURAL LANGUAGE → PY CODE ----------
def _looks_like_python(s: str) -> bool:
    return "bpy." in s or s.strip().startswith(("import ", "obj =", "for ", "if ", "while ", "class ", "def "))

def _parse_distance(token: str) -> float:
    t = token.strip().lower().replace(" ", "")
    m = re.match(r"^(-?\d+(?:\.\d+)?)(mm|cm|m)?$", t)
    if not m: return None
    val = float(m.group(1)); unit = m.group(2) or "m"
    return val/1000.0 if unit=="mm" else (val/100.0 if unit=="cm" else val)

def _parse_angle(token: str) -> float:
    t = token.strip().lower().replace(" ", "")
    m = re.match(r"^(-?\d+(?:\.\d+)?)(deg|rad)?$", t)
    if not m: return None
    val = float(m.group(1)); unit = (m.group(2) or "deg")
    return val if unit=="rad" else val*3.141592653589793/180.0

def _resolve_names(name_hint: str, scene_objs: list, selection: dict) -> list[str]:
    nh = (name_hint or "").strip().lower()
    obj_names = [o["name"] for o in scene_objs]
    if nh in ("active",):
        a = selection.get("active")
        return [a] if a else []
    if nh in ("selected","selection"):
        return selection.get("selected", [])
    if "*" in nh or "?" in nh:
        regex = "^" + re.escape(nh).replace(r"\*", ".*").replace(r"\?", ".") + "$"
        return [n for n in obj_names if re.match(regex, n.lower())]
    for n in obj_names:
        if n.lower()==nh: return [n]
    starts = [n for n in obj_names if n.lower().startswith(nh)]
    return starts if starts else []

def _apply_except(names: list[str], clause: str) -> list[str]:
    if not clause: return names
    killers = []
    for token in [s.strip() for s in clause.split(",") if s.strip()]:
        if "*" in token or "?" in token:
            rx = "^" + re.escape(token).replace(r"\*", ".*").replace(r"\?", ".") + "$"
            killers.extend([n for n in names if re.match(rx, n.lower())])
        else:
            killers.extend([n for n in names if n.lower()==token.lower()])
    return [n for n in names if n not in killers]

def _emit_move_global(n: str, axis: str, meters: float) -> str:
    comp = {"x":0,"y":1,"z":2}[axis]
    return (
        f'obj = bpy.data.objects.get("{n}")\n'
        f'if obj:\n'
        f'    loc = list(obj.location)\n'
        f'    loc[{comp}] = loc[{comp}] + {meters}\n'
        f'    obj.location = loc\n'
    )

def _emit_move_local(n: str, axis: str, meters: float) -> str:
    comp = {"x":0,"y":1,"z":2}[axis]
    return (
        f'from mathutils import Vector\n'
        f'obj = bpy.data.objects.get("{n}")\n'
        f'if obj:\n'
        f'    dv = [0.0,0.0,0.0]\n'
        f'    dv[{comp}] = {meters}\n'
        f'    world_dv = obj.matrix_world.to_3x3() @ Vector(dv)\n'
        f'    obj.location = obj.location + world_dv\n'
    )

def _emit_rotate(n: str, axis: str, radians: float, space: str) -> str:
    comp = {"x":0,"y":1,"z":2}[axis]
    # For now treat local/global the same on Euler; local is typical
    return (
        f'obj = bpy.data.objects.get("{n}")\n'
        f'if obj:\n'
        f'    r = list(obj.rotation_euler)\n'
        f'    r[{comp}] = r[{comp}] + {radians}\n'
        f'    obj.rotation_euler = r\n'
    )

def _emit_scale(n: str, factor: float) -> str:
    return (
        f'obj = bpy.data.objects.get("{n}")\n'
        f'if obj:\n'
        f'    s = obj.scale\n'
        f'    obj.scale = ({factor}*s.x, {factor}*s.y, {factor}*s.z)\n'
    )

def _split_actions(text: str) -> list[str]:
    return [p.strip() for p in re.split(r"\band\b", text, maxsplit=1) if p.strip()]

def translate_nlp_to_code(line: str, scene: dict, selection: dict) -> str:
    """
    Examples:
      move selected up 10cm
      move active +z 0.2 local
      move cube.0* forward 0.1 except cube.003
      rotate cube 45deg z local
      scale selected 1.2x
      scale Cube* 120%
      move cube up 0.1 and rotate cube 15deg x
    """
    text = line.strip()
    if not text: return ""
    low = text.lower()

    # synonyms
    low = (low.replace("raise","move")
              .replace("lower","move")
              .replace("translate","move")
              .replace("nudge","move")
              .replace("turn","rotate")
              .replace("spin","rotate"))

    scene_objs = scene.get("objects", [])
    sel = selection or {}

    codes = []
    for action in _split_actions(low):
        # MOVE
        m = re.match(
            r'^(move)\s+(.+?)\s+(up|down|\+?z|\-z|left|right|\+?x|\-x|forward|back|\+?y|\-y)\s+([-\w\.]+)\s*(local|global)?(?:\s+except\s+(.+))?$',
            action)
        if m:
            target_hint, dir_tok, dist_tok, space, exc = m.group(2), m.group(3), m.group(4), (m.group(5) or "global"), m.group(6)
            dist = _parse_distance(dist_tok)
            if dist is None: 
                print(f"⚠️  Bad distance: {dist_tok}"); 
                continue
            axis, sign = None, 1.0
            if dir_tok in ("up","+z","z"): axis, sign = "z", 1.0
            elif dir_tok in ("down","-z"): axis, sign = "z", -1.0
            elif dir_tok in ("right","+x","x"): axis, sign = "x", 1.0
            elif dir_tok in ("left","-x"): axis, sign = "x", -1.0
            elif dir_tok in ("forward","+y","y"): axis, sign = "y", 1.0
            elif dir_tok in ("back","-y"): axis, sign = "y", -1.0
            names = _apply_except(_resolve_names(target_hint, scene_objs, sel), exc or "")
            if not names:
                print(f"⚠️  No targets for: {target_hint}")
                continue
            for n in names:
                codes.append(_emit_move_local(n, axis, sign*dist) if space=="local" else _emit_move_global(n, axis, sign*dist))
            continue

        # ROTATE
        m = re.match(r'^(rotate)\s+(.+?)\s+([-\w\.]+)\s*(deg|rad|degrees?)?\s*([xyz])?\s*(local|global)?$', action)
        if m:
            target_hint = m.group(2)
            angle_tok   = m.group(3) + (m.group(4) or "")
            axis_tok    = (m.group(5) or "z").lower()
            space       = (m.group(6) or "local").lower()
            ang = _parse_angle(angle_tok)
            if ang is None:
                print(f"⚠️  Bad angle: {angle_tok}")
                continue
            names = _resolve_names(target_hint, scene_objs, sel)
            for n in names:
                codes.append(_emit_rotate(n, axis_tok, ang, space))
            continue

        # SCALE: "1.2x" or "120%"
        m = re.match(r'^(scale)\s+(.+?)\s+([0-9\.]+)\s*(x|%)$', action)
        if m:
            target_hint = m.group(2)
            val = float(m.group(3))
            factor = val/100.0 if m.group(4)=="%" else val
            names = _resolve_names(target_hint, scene_objs, sel)
            for n in names:
                codes.append(_emit_scale(n, factor))
            continue

        # Not parsed & not obvious Python → skip
        if not _looks_like_python(action):
            print(f"⏭️  Skipping unrecognized natural command: {action}")
            continue

        # Treat as literal Python
        codes.append(text)

    return "\n".join(codes)

# ---------- main loop ----------
def run_agent():
    print("🚀 Queue Agent started. Ctrl+C to stop.")
    paused = False
    step_mode = False

    try:
        while True:
            # live control
            ctrl = _read_control()
            if ctrl == "STOP":
                print("🛑 Received STOP. Exiting.")
                break
            elif ctrl == "PAUSE":
                paused = True; step_mode = False
                print("⏸️ PAUSE"); open(CONTROL_FILE, "w", encoding="utf-8").close()
            elif ctrl == "RESUME":
                paused = False; step_mode = False
                print("▶️ RESUME"); open(CONTROL_FILE, "w", encoding="utf-8").close()
            elif ctrl == "STEP":
                paused = False; step_mode = True
                print("🔂 STEP (one block)"); open(CONTROL_FILE, "w", encoding="utf-8").close()

            if paused:
                time.sleep(0.1); 
                continue

            fast, delay_ms, burst_size, confirm_every = _read_behavior()
            prev_mtime = _mtime(SCENE_FILE)

            sends_this_tick = 0
            conf_counter = 0

            while sends_this_tick < burst_size:
                block = _pop_queue_block()
                if not block:
                    break

                # Translate natural language lines now (fresh scene/selection)
                scene      = _read_json(SCENE_FILE, {})
                selection  = _read_json(SELECTED_FILE, {})
                translated = []
                for ln in block:
                    if _looks_like_python(ln):
                        translated.append(ln)
                    else:
                        code = translate_nlp_to_code(ln, scene, selection)
                        if code:
                            translated.append(code)
                        else:
                            print(f"⏭️  Skipping unrecognized natural command: {ln}")
                if not translated:
                    continue

                # Animator poke (optional) — harmless if keyframe mode is off
                beh = selection.get("behavior", {})
                if beh.get("animator_mode", False):
                    translated.insert(0, "scene=bpy.context.scene\nscene.frame_set(scene.frame_current)")

                runid = int(time.time() * 1000)
                cmd = "\n".join(translated) + f"\n# runid:{runid}\n"

                head = (block[0][:100] + (" ..." if len(block) > 1 else ""))
                print("→ Running:", head)
                _write_input_and_trigger(cmd)

                sends_this_tick += 1
                conf_counter += 1

                if (conf_counter % confirm_every == 0) or (sends_this_tick == burst_size):
                    ok = _wait_for_blender(prev_mtime, timeout=1.2 if fast else 6.0)
                    prev_mtime = _mtime(SCENE_FILE)
                    if not ok:
                        print("⚠️ Blender did not confirm in time (continuing).")

                if fast:
                    time.sleep(0.01)  # tiny yield for Blender timer

            # idle if nothing was sent
            if sends_this_tick == 0:
                time.sleep(0.03 if fast else max(0.1, delay_ms/1000.0))

            if step_mode:
                paused = True
                print("⏸️ Auto-paused after STEP.")

            if not fast:
                time.sleep(max(0.05, delay_ms/1000.0))

    except KeyboardInterrupt:
        print("👋 Stopped by user.")

if __name__ == "__main__":
    run_agent()
