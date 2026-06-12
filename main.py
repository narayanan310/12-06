"""
main.py
Edge AI Automotive Cockpit Assistant — main orchestrator.

Pipeline (per turn, in priority order)
────────────────────────────────────────
  Guard 0   : Gibberish filter
  Stage 0   : Macro Engine          — multi-action sequences
  Stage 1a  : Preference Memory     — remember / recall settings
  Stage 1b  : Dialogue Repair       — undo / actually / go back
  Stage 1c  : Dialogue Confirm      — yes / confirm (pending intent)
  Stage 1d  : Conversation Layer    — small talk, out-of-scope replies
  Stage 2   : Intent Splitter       — compound command decomposition
  Per-clause:
    Stage 3 : Context Window        — relative commands (domain-aware)
    Stage 4 : Context Resolver      — semantic comfort/safety/wellness
    Stage 5 : Regex                 — explicit deterministic commands
    Stage 6 : SLM                   — novel/ambiguous fallback
  Safety    : SafetySupervisor      — sits between every resolver and CAN

Fixes applied
─────────────
- STATUS_QUERY intents (from regex_mapper) now handled in _execute_intent:
  routes to StateManager snapshot instead of crashing on bus.publish(None).
- MACRO_RESET intents (from regex_mapper) now handled in _execute_intent:
  triggers macro_eng reset sequence instead of crashing on bus.publish(None).
  Because MacroEngine is not available inside _execute_intent, MACRO_RESET is
  handled at the call-site in the main loop (same pattern as SAFETY_ALERT) by
  returning the command upward — _execute_intent returns early with a sentinel
  and main() dispatches the reset macro directly.
  Simpler alternative adopted: _execute_intent accepts an optional `sm`
  reference (already present) and handles STATUS_QUERY inline; MACRO_RESET
  is caught before _execute_intent is called in the main loop.
"""

import asyncio
import time

from state_manager      import StateManager
from virtual_can_bus    import VirtualCANBus
from vehicle_modules    import ClimateModule, SunroofModule, LightingModule
from macro_engine       import MacroEngine
from conversation_layer import ConversationLayer
from context_window     import ContextWindow
from context_resolver   import ContextResolver
from regex_mapper       import RegexIntentResolver
from slm_resolver       import SLMIntentResolver
from safety_supervisor  import SafetySupervisor, is_gibberish
from intent_splitter    import split_intents
from dialogue_manager   import DialogueManager, DialogueState
from preference_memory  import PreferenceMemory

# ── Special commands that must never reach bus.publish ────────────────────────
# These are returned by regex_mapper with can_id=None and require bespoke handling.
_NO_DISPATCH_CMDS = {"SAFETY_ALERT", "UNKNOWN", "STATUS_QUERY", "MACRO_RESET"}


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


# ── CAN dispatch ──────────────────────────────────────────────────────────────

async def _dispatch(bus: VirtualCANBus, intent: dict) -> None:
    await bus.publish(intent["can_id"], intent["command"], intent["value"])
    await asyncio.sleep(0.1)


# ── SLM health check ──────────────────────────────────────────────────────────

async def _wait_for_slm(slm: SLMIntentResolver, timeout_s: int = 60) -> bool:
    print("[System] Checking SLM server...")
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if slm.health_check():
            print("[System] SLM server ready.")
            return True
        await asyncio.sleep(2)
    print("[System] WARNING: SLM not responding. Running in deterministic-only mode.")
    return False


# ── Per-clause resolver (stages 3–6) ─────────────────────────────────────────

def _resolve_clause(
    text:    str,
    ctx_win: ContextWindow,
    ctx_res: ContextResolver,
    regex:   RegexIntentResolver,
    slm:     SLMIntentResolver,
    slm_ok:  bool,
    domain:  str | None = None,
) -> dict | None:
    # Stage 3: Context window — relative commands (domain-aware)
    intent = ctx_win.resolve_relative(text, domain=domain)
    if intent:
        return intent

    # Stage 4: Context resolver — semantic comfort/safety/wellness
    intent = ctx_res.resolve(text)
    if intent:
        return intent

    # Stage 5: Regex — explicit deterministic commands
    intent = regex.resolve(text)
    if intent:
        return intent

    # Stage 6: SLM — novel fallback
    if slm_ok:
        print("[System] Routing to SLM...")
        return slm.resolve(text)

    return None


# ── Intent execution (shared by both single and multi-intent paths) ───────────

async def _execute_intent(
    clause:      str,
    intent:      dict,
    bus:         VirtualCANBus,
    safety:      SafetySupervisor,
    ctx_win:     ContextWindow,
    dlg:         DialogueManager,
    sm:          StateManager,
    macro_eng:   MacroEngine,
    show_clause: bool = False,
) -> None:
    """
    Run safety check, dispatch to CAN, update dialogue state.

    Handles all special commands (SAFETY_ALERT, UNKNOWN, STATUS_QUERY,
    MACRO_RESET) before touching the CAN bus so bus.publish() is never
    called with a None can_id.
    """
    if show_clause:
        print(f'\n[Clause] "{clause}"')

    _print_intent(intent)

    # Wellness message (non-blocking — runs alongside vehicle action)
    if "_wellness_msg" in intent:
        _say(intent["_wellness_msg"])

    # Extra safety warning from context_resolver
    if "_warning" in intent:
        print(f"[⚠ Warning] {intent['_warning']}")

    cmd = intent.get("command")

    # ── Special commands — never reach bus.publish ────────────────────────

    if cmd == "SAFETY_ALERT":
        print("[SAFETY] Mechanical concern — please pull over safely.")
        _say("I noticed a potential safety concern. Please check your vehicle.")
        return

    if cmd == "UNKNOWN":
        print("[System] Out of scope — no vehicle action taken.")
        _say("I can only control vehicle systems. "
             "Try: temperature, sunroof, lights, or fan speed.")
        return

    if cmd == "STATUS_QUERY":
        # FIX: was falling through to _dispatch with can_id=None → crash.
        # Now prints the live vehicle state snapshot instead.
        print("\n[Vehicle State]")
        print(sm.snapshot())
        return

    if cmd == "MACRO_RESET":
        # FIX: was falling through to _dispatch with can_id=None → crash.
        # Delegate to MacroEngine which owns the reset sequence.
        reset_macro = macro_eng.match("reset")
        if reset_macro:
            print(f"\n[Macro] {reset_macro['display']}")
            _say(reset_macro["speech"])
            await macro_eng.execute(bus, reset_macro)
        else:
            _say("Reset acknowledged — no reset macro defined.")
        return

    # ── Safety gate ───────────────────────────────────────────────────────

    pre_state        = sm.get_state()
    allowed, warning = safety.check(intent)

    if warning:
        print(f"[Safety] {warning}")

    if not allowed:
        print("[System] Command blocked by safety supervisor.")
        return

    if intent.get("_at_limit"):
        _say(f"Already at the limit ({intent['value']}).")
        # Still dispatch — ECU handles idempotent write cleanly
    else:
        print(f"[CAN] {cmd} → {intent['can_id']} (value={intent['value']})")

    await _dispatch(bus, intent)
    ctx_win.push(clause, intent)
    dlg.record(clause, intent, pre_state)

    # Proactive nudge
    nudge = ctx_win.check_proactive_nudge()
    if nudge:
        _say(nudge)


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
    slm_eng   = SLMIntentResolver()
    safety    = SafetySupervisor(sm)
    dlg       = DialogueManager()
    prefs     = PreferenceMemory()

    bus_task  = asyncio.create_task(bus.start())
    slm_ready = await _wait_for_slm(slm_eng, timeout_s=60)

    print("\n" + "=" * 50)
    print(" VEHICLE SYSTEMS ONLINE                          ")
    print(" Macros  : dog mode | bye | good night           ")
    print("           focus mode | reset                    ")
    print(" Memory  : 'remember this' | 'my usual settings' ")
    print(" Repair  : 'undo that' | 'go back' | 'actually'  ")
    print(" Info    : 'help' | 'status'                     ")
    print(" Quit    : 'exit'                                 ")
    print("=" * 50 + "\n")

    # ── Helper: wraps _execute_intent with macro_eng already bound ────────
    async def _exec(
        clause: str,
        intent: dict,
        show_clause: bool = False,
    ) -> None:
        await _execute_intent(
            clause, intent, bus, safety, ctx_win, dlg, sm,
            macro_eng, show_clause=show_clause,
        )

    while True:
        try:
            raw = await asyncio.to_thread(input, "Driver: ")
        except (EOFError, KeyboardInterrupt):
            break

        raw = raw.strip()
        if not raw:
            continue
        if raw.lower() in ("exit", "quit"):
            break

        # ── Guard: gibberish ──────────────────────────────────────────────
        if is_gibberish(raw):
            _say("I didn't catch that — could you try again?")
            print("\n" + "-" * 50)
            continue

        # ── Stage 0: Macro Engine ─────────────────────────────────────────
        macro = macro_eng.match(raw)
        if macro:
            print(f"\n[Macro] {macro['display']}")
            _say(macro["speech"])
            await macro_eng.execute(bus, macro)
            await asyncio.sleep(0.1)
            print("\n" + "-" * 50)
            continue

        # ── Stage 1a: Preference Memory ───────────────────────────────────
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
                        await bus.publish(
                            action["can_id"], action["command"], action["value"]
                        )
                        await asyncio.sleep(0.12)
                else:
                    _say("No preferences saved yet. "
                         "Say 'remember this' to save current settings.")

            print("\n" + "-" * 50)
            continue

        # ── Stage 1b: Dialogue Repair ─────────────────────────────────────
        if dlg.is_repair(raw):
            action, undo_intent = dlg.resolve_repair(raw)

            if action == "cancel_pending":
                dlg.clear_pending()
                _say("Cancelled. What would you like to do instead?")

            elif action in ("undo", "undo_last") and undo_intent:
                _say("Reversing the last action.")
                pre_state        = sm.get_state()
                allowed, warning = safety.check(undo_intent)
                if warning:
                    print(f"[Safety] {warning}")
                if allowed:
                    print(
                        f"[CAN] {undo_intent['command']} → "
                        f"{undo_intent['can_id']} "
                        f"(value={undo_intent['value']})"
                    )
                    await _dispatch(bus, undo_intent)
                    ctx_win.push(raw, undo_intent)
                    dlg.record(raw, undo_intent, pre_state)
                else:
                    print("[System] Undo blocked by safety supervisor.")

            elif action == "nothing_to_undo":
                _say("Nothing to undo — no recent action recorded.")

            else:
                # 'unclear' — try to re-route as a regular command
                intent = _resolve_clause(
                    raw, ctx_win, ctx_res, regex_eng, slm_eng, slm_ready
                )
                if intent:
                    await _exec(raw, intent)
                else:
                    _say("I'm not sure what to adjust. "
                         "Could you be more specific?")

            print("\n" + "-" * 50)
            continue

        # ── Stage 1c: Pending confirmation ────────────────────────────────
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

        # ── Stage 1d: Conversation Layer ──────────────────────────────────
        reply = conv_lay.respond(raw)
        if reply:
            if reply == "_STATE_DUMP":
                print("\n[Vehicle State]")
                print(sm.snapshot())
            else:
                _say(reply)
            print("\n" + "-" * 50)
            continue

        # ── Multi-intent split ────────────────────────────────────────────
        clauses = split_intents(raw)

        # Infer domain hint from the full raw text (for relative resolution)
        domain_hint = dlg.extract_domain_hint(raw)

        resolved: list[tuple[str, dict]] = []
        failed:   list[str]              = []

        for clause in clauses:
            intent = _resolve_clause(
                clause, ctx_win, ctx_res, regex_eng, slm_eng, slm_ready,
                domain=domain_hint,
            )
            if intent:
                resolved.append((clause, intent))
            else:
                failed.append(clause)

        # Safety-first ordering within compound commands
        resolved.sort(
            key=lambda ci: 0 if ci[1].get("priority") == "safety" else 1
        )

        if not resolved and not failed:
            print("\n[System] No command recognised.")
            _say("Sorry, I didn't understand that. "
                 "Try: temperature, sunroof, lights, or say 'help'.")
            print("\n" + "-" * 50)
            continue

        for clause, intent in resolved:
            await _exec(clause, intent, show_clause=(len(clauses) > 1))

        for clause in failed:
            if len(clauses) > 1:
                print(f'\n[Clause] "{clause}" — could not resolve.')

        print("\n" + "-" * 50)

    # ── Graceful shutdown ─────────────────────────────────────────────────
    print("\nShutting down vehicle systems...")
    bus_task.cancel()
    try:
        await bus_task
    except asyncio.CancelledError:
        pass
    print("Goodbye.")


if __name__ == "__main__":
    asyncio.run(main())