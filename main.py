"""
main.py
Edge AI Automotive Cockpit Assistant — main orchestrator.
"""

import asyncio
import time
import queue
import threading

# Audio fallback in case dependencies aren't installed yet
try:
    from audio_io import AudioIO
    audio_sys = AudioIO()
except Exception as e:
    print(f"[Warning] Voice system not loaded: {e}. Running in text-only mode.")
    audio_sys = None

from state_manager      import StateManager
from virtual_can_bus    import VirtualCANBus
from vehicle_modules    import ClimateModule, SunroofModule, LightingModule
from macro_engine       import MacroEngine
from conversation_layer import ConversationLayer
from context_window     import ContextWindow
from context_resolver   import ContextResolver
from regex_mapper       import RegexIntentResolver
from rag_resolver       import RAGResolver
from slm_resolver       import SLMIntentResolver
from safety_supervisor  import SafetySupervisor, is_gibberish
from intent_splitter    import split_intents
from dialogue_manager   import DialogueManager, DialogueState
from preference_memory  import PreferenceMemory

# ── Special commands that must never reach bus.publish ────────────────────────
_NO_DISPATCH_CMDS = {
    "SAFETY_ALERT", 
    "UNKNOWN", 
    "STATUS_QUERY", 
    "MACRO_RESET",
    "RAG_RESPONSE",
    "INCOMPLETE_COMMAND",
    "FRUSTRATION_DETECTED",
}

# ── Display helpers ───────────────────────────────────────────────────────────

def _print_intent(intent: dict) -> None:
    src      = intent.get("handled_by", "?")
    lat      = intent.get("latency",    "?")
    conf     = intent.get("confidence")
    pri      = intent.get("priority",   "")
    conf_str = f"  confidence={conf:.0%}" if conf is not None else ""
    pri_str  = f"  [{pri.upper()}]"       if pri              else ""
    print(f"\n[Intent] source={src}  latency={lat}{conf_str}{pri_str}")
    print(f"[Intent] reason: {intent.get('reason', '')}")


def _say(msg: str) -> None:
    print(f'[Assistant] "{msg}"')
    if audio_sys:
        audio_sys.speak(msg)

# ── Confirmation message generator ────────────────────────────────────────────

_UNIT = {
    "SET_TEMPERATURE": "°C", "SET_FAN_SPEED": "", "SET_POSITION": "%",
    "SET_BRIGHTNESS": "%", "TOGGLE_AC": "", "SET_HEADLIGHTS": "",
}

_LABEL = {
    "SET_TEMPERATURE": "Temperature", "SET_FAN_SPEED": "Fan speed",
    "SET_POSITION": "Sunroof", "SET_BRIGHTNESS": "Brightness",
    "TOGGLE_AC": "AC", "SET_HEADLIGHTS": "Headlights",
}

def _confirm_message(intent: dict, was_no_change: bool, prev_value: int | None = None) -> str:
    cmd   = intent.get("command", "")
    val   = intent.get("value")
    label = _LABEL.get(cmd, cmd.replace("_", " ").title())
    unit  = _UNIT.get(cmd, "")

    if intent.get("_at_limit"):
        direction = "maximum" if (prev_value is not None and val >= prev_value) else "minimum"
        return f"{label} is already at its {direction} ({val}{unit})."
    if was_no_change:
        return f"{label} is already at {val}{unit} — no change."
    if cmd == "TOGGLE_AC":
        return "AC turned on." if val else "AC turned off."
    if cmd == "SET_HEADLIGHTS":
        return "Headlights turned on." if val else "Headlights turned off."
    if cmd == "SET_POSITION":
        if val == 0: return "Sunroof closed."
        if val == 100: return "Sunroof fully open."
        return f"Sunroof opened to {val}%."
    if intent.get("handled_by") == "ContextWindow" and prev_value is not None:
        if val > prev_value: return f"{label} increased to {val}{unit}."
        if val < prev_value: return f"{label} decreased to {val}{unit}."
        return f"{label} set to {val}{unit}."
    

# ── CAN dispatch ──────────────────────────────────────────────────────────────
async def _dispatch(bus: VirtualCANBus, intent: dict) -> None:
    await bus.publish(intent["can_id"], intent["command"], intent["value"])
    await asyncio.sleep(0.1)

# ── Per-clause resolver (stages 3–6) ─────────────────────────────────────────
def _resolve_clause(
    text: str, ctx_win: ContextWindow, ctx_res: ContextResolver,
    regex: RegexIntentResolver, rag, slm: SLMIntentResolver, slm_ok: bool,
    domain: str | None = None,
) -> dict | None:
    intent = ctx_win.resolve_relative(text, domain=domain)
    if intent: return intent

    intent = ctx_res.resolve(text)
    if intent: return intent

    intent = regex.resolve(text)
    if intent: return intent

    rag_triggers = ["manual", "guide", "search", "look up", "how to", "what is"]
    if any(trigger in text.lower() for trigger in rag_triggers):
        print("[System] RAG trigger detected. Searching knowledge base...")
        intent = rag.resolve(text)
        if intent: return intent

    if slm_ok:
        words = text.strip().split()
        if len(words) >= 2 and any(w.isalpha() for w in words):
            print("[System] Routing to SLM...")
            return slm.resolve(text)
        return None

# ── Intent execution ──────────────────────────────────────────────────────────
async def _execute_intent(
    clause: str, intent: dict, bus: VirtualCANBus, safety: SafetySupervisor,
    ctx_win: ContextWindow, dlg: DialogueManager, sm: StateManager,
    macro_eng: MacroEngine, show_clause: bool = False,
) -> None:
    if show_clause:
        print(f'\n[Clause] "{clause}"')

    _print_intent(intent)

    if "_wellness_msg" in intent: _say(intent["_wellness_msg"])
    if "_warning" in intent: print(f"[⚠ Warning] {intent['_warning']}")

    cmd = intent.get("command")

    if cmd == "INCOMPLETE_COMMAND":
        verb = intent.get("verb", "do")
        _say(f"{verb.capitalize()} what?")
        return
    if cmd == "SAFETY_ALERT":
        _say("I noticed a potential safety concern. Please check your vehicle.")
        return
    if cmd == "UNKNOWN":
        _say("I can only control vehicle systems. Try: temperature, sunroof, lights, or fan speed.")
        return
    if cmd == "STATUS_QUERY":
        print("\n[Vehicle State]")
        print(sm.snapshot())
        return
    if cmd == "MACRO_RESET":
        reset_macro = macro_eng.match("reset")
        if reset_macro:
            print(f"\n[Macro] {reset_macro['display']}")
            _say(reset_macro["speech"])
            await macro_eng.execute(bus, reset_macro)
        else:
            _say("Reset acknowledged — no reset macro defined.")
        return
    if cmd == "RAG_RESPONSE":
        answer = intent.get("answer")
        if answer: _say(answer)
        else: _say("I couldn't find that information.")
        return
    if cmd == "FRUSTRATION_DETECTED":
        # You can randomize these responses to make it feel more natural
        import random
        apologies = [
            "I'm really sorry, I know I can be frustrating sometimes. Let's try that again.",
            "My bad. I'm still learning. What did you want me to do?",
            "Sorry about that. I misheard you. Could you rephrase your command?",
            "I hear you. Let me reset my context. What can I help with?"
        ]
        _say(random.choice(apologies))
        
        # Optional: Clear the dialogue history so the AI gets a "fresh start"
        dlg.clear_pending()
        ctx_win.clear() 
        return

    pre_state = sm.get_state()
    allowed, warning = safety.check(intent)

    if warning: print(f"[Safety] {warning}")
    if not allowed:
        _say("I can't do that right now — it's been blocked for safety.")
        return

    cmd = intent.get("command", "")
    prev_val = sm.get_state().get(cmd)

    if intent.get("_at_limit"):
        _say(f"Already at the limit ({intent['value']}).")
    else:
        print(f"[CAN] {cmd} → {intent['can_id']} (value={intent['value']})")

    await _dispatch(bus, intent)

    post_state = sm.get_state()
    was_no_change = (pre_state == post_state) and not intent.get("_at_limit")

    confirm = _confirm_message(intent, was_no_change, prev_value=prev_val)
    _say(confirm)

    ctx_win.push(clause, intent)
    dlg.record(clause, intent, pre_state)

    nudge = ctx_win.check_proactive_nudge()
    if nudge: _say(nudge)

# ── Main loop ─────────────────────────────────────────────────────────────────
async def main() -> None:
    print("\nInitializing Edge AI Automotive Cockpit...")
    print("=" * 50)

    sm  = StateManager()
    bus = VirtualCANBus()
    ClimateModule(sm, bus)
    SunroofModule(sm, bus)
    LightingModule(sm, bus)

    macro_eng = MacroEngine()
    conv_lay  = ConversationLayer()
    ctx_win   = ContextWindow()
    ctx_res   = ContextResolver()
    regex_eng = RegexIntentResolver()
    rag_eng   = RAGResolver()
    slm_eng   = SLMIntentResolver()
    safety    = SafetySupervisor(sm)
    dlg       = DialogueManager()
    prefs     = PreferenceMemory()

    bus_task  = asyncio.create_task(bus.start())
    
    # Bypass health check to load instantly on Raspberry Pi
    slm_ready = True
    print("[System] Bypassing SLM health check. UI loading immediately.")

    print("\n" + "=" * 50)
    print(" VEHICLE SYSTEMS ONLINE                          ")
    print(" Macros  : dog mode | bye | good night           ")
    print("           focus mode | reset                    ")
    print(" Memory  : 'remember this' | 'my usual settings' ")
    print(" Repair  : 'undo that' | 'go back' | 'actually'  ")
    print(" Info    : 'help' | 'status'                     ")
    print(" Quit,bye    : 'exit'                                 ")
    print("=" * 50 + "\n")

    # ── Input Threading Setup ─────────────────────────────────────────────
    # We use a queue to safely accept both Voice and Keyboard input at the same time
    cmd_queue = queue.Queue()

    def keyboard_worker():
        while True:
            try:
                txt = input()
                if txt.strip():
                    # We echo the text explicitly so the log looks clean
                    print(f"\nDriver (Text): {txt.strip()}")
                    cmd_queue.put(txt.strip())
            except EOFError:
                break

    threading.Thread(target=keyboard_worker, daemon=True).start()

    if audio_sys:
        def voice_worker():
            while True:
                txt = audio_sys.listen()
                if txt:
                    print(f"\nDriver (Voice): {txt}")
                    cmd_queue.put(txt)
        threading.Thread(target=voice_worker, daemon=True).start()

    print("[System] Ready! You can TYPE in the terminal or SPEAK into the microphone.")

    async def _exec(clause: str, intent: dict, show_clause: bool = False) -> None:
        await _execute_intent(clause, intent, bus, safety, ctx_win, dlg, sm, macro_eng, show_clause=show_clause)

    while True:
        try:
            # Wait for either the voice mic or the keyboard to drop something in the queue
            raw = await asyncio.to_thread(cmd_queue.get)
        except (EOFError, KeyboardInterrupt):
            break

        if raw.lower() in ("exit", "quit","bye","goodbye"):
            break

        if is_gibberish(raw):
            _say("I didn't catch that — could you try again?")
            print("\n" + "-" * 50)
            continue

        macro = macro_eng.match(raw)
        if macro:
            print(f"\n[Macro] {macro['display']}")
            _say(macro["speech"])
            await macro_eng.execute(bus, macro)
            await asyncio.sleep(0.1)
            print("\n" + "-" * 50)
            continue

        pref_action = prefs.detect(raw)
        if pref_action:
            state = sm.get_state()
            if pref_action == "query":
                print(f"\n{prefs.describe()}")
            elif pref_action == "save":
                msg = prefs.save_all(state)
                _say(msg)
            elif pref_action.startswith("save_key:"):
                key = pref_action.split(":", 1)[1]
                msg = prefs.save_key(key, state)
                _say(msg)
            elif pref_action == "load":
                actions = prefs.load_all()
                if actions:
                    _say("Restoring your saved preferences.")
                    for action in actions:
                        await bus.publish(action["can_id"], action["command"], action["value"])
                        await asyncio.sleep(0.12)
                else:
                    _say("No preferences saved yet. Say 'remember this' to save current settings.")
            print("\n" + "-" * 50)
            continue

        if dlg.is_repair(raw):
            action, undo_intent = dlg.resolve_repair(raw)
            if action == "cancel_pending":
                dlg.clear_pending()
                _say("Cancelled. What would you like to do instead?")
            elif action in ("undo", "undo_last") and undo_intent:
                _say("Reversing the last action.")
                pre_state = sm.get_state()
                allowed, warning = safety.check(undo_intent)
                if warning: print(f"[Safety] {warning}")
                if allowed:
                    print(f"[CAN] {undo_intent['command']} → {undo_intent['can_id']} (value={undo_intent['value']})")
                    await _dispatch(bus, undo_intent)
                    ctx_win.push(raw, undo_intent)
                    dlg.record(raw, undo_intent, pre_state)
                else:
                    print("[System] Undo blocked by safety supervisor.")
            elif action == "nothing_to_undo":
                _say("Nothing to undo — no recent action recorded.")
            else:
                intent = _resolve_clause(raw, ctx_win, ctx_res, regex_eng, rag_eng, slm_eng, slm_ready)
                if intent: await _exec(raw, intent)
                else: _say("I'm not sure what to adjust. Could you be more specific?")
            print("\n" + "-" * 50)
            continue

        if dlg.state == DialogueState.PENDING_CONFIRM:
            if dlg.is_confirmation(raw):
                pending = dlg.pop_pending()
                if pending:
                    _say("Confirmed.")
                    await _exec(raw, pending)
            else:
                dlg.clear_pending()
                _say("Understood — action cancelled.")
            print("\n" + "-" * 50)
            continue

        reply = conv_lay.respond(raw)
        if reply:
            if reply == "_STATE_DUMP":
                print("\n[Vehicle State]")
                print(sm.snapshot())
            else:
                _say(reply)
            print("\n" + "-" * 50)
            continue

        clauses = split_intents(raw)
        domain_hint = dlg.extract_domain_hint(raw)
        resolved = []
        failed = []

        for clause in clauses:
            intent = _resolve_clause(clause, ctx_win, ctx_res, regex_eng, rag_eng, slm_eng, slm_ready, domain=domain_hint)
            if intent: resolved.append((clause, intent))
            else: failed.append(clause)

        resolved.sort(key=lambda ci: 0 if ci[1].get("priority") == "safety" else 1)

        if not resolved and not failed:
            print("\n[System] No command recognised.")
            _say("I didn't understand that — try saying something like 'set temperature to 22' or 'open sunroof'.")
            print("\n" + "-" * 50)
            continue

        for clause, intent in resolved:
            await _exec(clause, intent, show_clause=(len(clauses) > 1))

        for clause in failed:
            if len(clauses) > 1:
                print(f'\n[Clause] "{clause}" — could not resolve.')
                _say(f"I couldn't understand \"{clause}\" — please try again.")
            else:
                _say("I couldn't do that — please rephrase or try 'help'.")

        print("\n" + "-" * 50)

    print("\nShutting down vehicle systems...")
    bus_task.cancel()
    try: await bus_task
    except asyncio.CancelledError: pass
    print("Goodbye.")

if __name__ == "__main__":
    asyncio.run(main())      