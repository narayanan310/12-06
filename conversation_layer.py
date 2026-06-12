"""
conversation_layer.py
Handles small talk, greetings, farewells, and out-of-scope requests.

Runs BEFORE the SLM so casual language never triggers a hallucinated
vehicle command.

New in this version
────────────────────
• Out-of-scope replies for all known non-vehicle domains.
• "I still need to drive home" — contextual safety response.
• "I meant inside / I meant the temperature" handled by DialogueManager
  (not here — those are repair signals).
"""

import random


_EXACT: dict[str, list[str]] = {
    "hi":    [
        "Hello! How can I help with the vehicle?",
        "Hi there! What would you like to adjust?",
    ],
    "hello": ["Hey! All systems online.", "Hello! What do you need?"],
    "hey":   ["Hey! What can I do for you?"],

    "thanks":    ["You're welcome!", "Happy to help!"],
    "thank you": ["Anytime!", "You're welcome!"],
    "ty":        ["You're welcome!"],

    "okay":    ["Got it.", "Understood."],
    "ok":      ["Got it.", "Understood."],
    "good":    ["Glad to hear it!"],
    "nice":    ["Thank you!"],
    "great":   ["Glad that worked!"],
    "awesome": ["Glad that worked!"],
    "perfect": ["Great — settings saved in memory."],
    "yep":     ["Got it."],
    "yeah":    ["Got it."],
    "yup":     ["Got it."],

    "how are you":  ["All vehicle systems running fine, thanks for asking!"],
    "are you there":["Yes, right here. What do you need?"],
    "you there":    ["Yes, right here. What do you need?"],

    "help": [
        "Controls: temperature, fan speed, AC on/off, sunroof, "
        "headlights, dashboard brightness.\n"
        "Macros   : dog mode | bye | good night | focus mode | reset.\n"
        "Memory   : 'remember this' | 'my usual settings'.\n"
        "Repair   : 'undo that' | 'go back' | 'actually'."
    ],

    "what can you do": [
        "I control climate (temperature, fan, AC), sunroof, "
        "headlights, and dashboard brightness. "
        "I also understand comfort expressions like 'I'm hot' or 'stuffy'. "
        "Say 'help' for a full list."
    ],
    "what do you do": [
        "I'm your in-vehicle assistant. Climate, sunroof, "
        "headlights, brightness. Say 'help' for details."
    ],

    "what time is it":        ["I don't have a clock — check your dashboard."],
    "what's the time":        ["I don't have a clock — check your dashboard."],
    "what's the temperature": [
        "I know the cabin setpoint. Say 'status' to see all current settings."
    ],
    "what is the current state": ["_STATE_DUMP"],
    "show state":                ["_STATE_DUMP"],
    "status":                    ["_STATE_DUMP"],

    "who are you":  ["I'm your vehicle assistant — climate, sunroof, headlights, brightness."],
    "what are you": ["An edge AI automotive assistant running locally on this vehicle's ECU."],
}

_PARTIAL: list[tuple[list[str], str]] = [
    # Greetings with time-of-day
    (["good morning"],          "Good morning! Ready to go?"),
    (["good afternoon"],        "Good afternoon! Comfortable drive ahead?"),
    (["good evening"],          "Good evening! Let's set up a smooth ride."),

    # Acknowledgements
    (["how's it going", "how is it going"], "All good — what do you need?"),
    (["sounds good", "that's good", "thats good"], "Great!"),
    (["not bad"],                           "Glad to hear it!"),

    # Jokes / entertainment
    (["joke", "funny", "make me laugh"],
     "I'd tell you a car joke, but I don't want to exhaust you. "
     "Now — back to the drive?"),

    # Music / audio
    (["play", "music", "song", "radio", "playlist", "spotify", "tune"],
     "I can't control audio yet. What vehicle system can I help with?"),

    # Phone / calls
    (["call ", "phone", "dial", "text message", "whatsapp", "ring"],
     "I can't make calls — I only control vehicle systems."),

    # Navigation
    (["navigate", "directions", "maps", "where is", "take me to", "route", "gps"],
     "Navigation isn't connected yet. I can help with climate, lights, and sunroof."),

    # Weather
    (["weather", "forecast", "will it rain", "rain today"],
     "I can't check weather — but I can adjust cabin temperature!"),

    # Food
    (["hungry", "food", "restaurant", "eat", "lunch", "dinner", "breakfast"],
     "I can't help with food — but I can cool down the cabin if you're warm!"),

    # Entertainment
    (["movie", "netflix", "youtube", "video", "watch", "stream"],
     "I can't control entertainment — just vehicle systems."),

    # "I still need to drive home" / "I need to keep driving"
    (["still need to drive", "need to drive home", "keep driving",
      "have to drive", "got to drive"],
     "Understood. I'll keep vehicle systems running. "
     "Let me know if you need temperature or lighting adjusted."),

    # Gratitude variations
    (["appreciate", "cheers", "ta "],  "You're welcome!"),

    # Wellness — conversational response only (action handled by context_resolver)
    (["i'm stressed", "im stressed", "feeling stressed"],
     "I hear you. I'll adjust the cabin to a calm temperature. "
     "Take a breath — you've got this."),
    (["headache", "head hurts", "migraine"],
     "Setting a comfortable temperature. "
     "Dim lighting might help too — say 'dim the screen' if you'd like."),
]


class ConversationLayer:
    def respond(self, text: str) -> str | None:
        """
        Returns a reply string, None if not conversational.
        Returns '_STATE_DUMP' for state queries (handled in main.py).
        """
        t = text.lower().strip()

        if t in _EXACT:
            return random.choice(_EXACT[t])

        for keywords, reply in _PARTIAL:
            if any(kw in t for kw in keywords):
                return reply

        return None
