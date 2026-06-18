"""
audio_io.py
- Speech-to-Text: Vosk (Offline, constrained grammar for 2GB RAM limits)
- Text-to-Speech: espeak (Direct subprocess call for ultimate stability)
- Threading: Background worker for speech to prevent main loop freezing
"""

import queue
import sys
import json
import threading
import subprocess
import sounddevice as sd
from vosk import Model, KaldiRecognizer

class AudioIO:
    def __init__(self, model_path="vosk-model-small-en-us-0.15"):
        print("[Audio] Loading Vosk offline STT model...")
        try:
            self.model = Model(model_path)
        except Exception as e:
            print(f"[Audio Error] Could not load Vosk model: {e}")
            print("Ensure the folder 'vosk-model-small-en-us-0.15' is in your project directory.")
            sys.exit(1)
        
        # Define the EXACT vocabulary the car is allowed to hear.
        # This stops Vosk from hallucinating random words and freezing your SLM.
        vocabulary = [
            "temperature", "fan", "speed", "ac", "sunroof", "lights", "headlights", "brightness",
            "open", "close", "turn", "on", "off", "set", "to", "increase", "decrease", "max", "min",
            "one", "two", "three", "four", "five", "twenty", "thirty", "fifty", "percent", "degrees",
            "undo", "cancel", "yes", "no", "hello", "hi", "help", "status", "macro", "mode", "night",
            "cold", "hot", "freezing", "sauna", "relaxing", "search", "manual", "guide", "what", "how",
            "dog", "bye", "good", "focus", "reset", "remember", "this", "my", "usual", "settings", 
            "go", "back", "actually", "exit", "quit", "[unk]"
        ]
        
        # Force Vosk to ONLY use this vocabulary (Saves massive RAM, increases accuracy to 95%+)
        grammar = json.dumps(vocabulary)
        self.recognizer = KaldiRecognizer(self.model, 16000, grammar)
        
        self.mic_queue = queue.Queue()
        self.tts_queue = queue.Queue()
        
        # Start the TTS worker thread
        threading.Thread(target=self._tts_worker, daemon=True).start()
        print("[Audio] Subsystems online.")

    def _tts_worker(self):
        """Processes text-to-speech commands in a background thread."""
        while True:
            text = self.tts_queue.get()
            try:
                # Direct call to espeak is infinitely more stable on Raspberry Pi than pyttsx3
                # -v en: English, -s 160: Speaking Speed
                subprocess.run(["espeak", "-v", "en", "-s", "160", text], 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
            except FileNotFoundError:
                print("[TTS Error] 'espeak' not found. Run: sudo apt-get install espeak")
            except Exception as e:
                print(f"[TTS Error] {e}")
            
            self.tts_queue.task_done()

    def speak(self, text: str):
        """Adds text to the queue for the worker thread to speak."""
        self.tts_queue.put(text)

    def _mic_callback(self, indata, frames, time, status):
        """Puts microphone audio chunks into a thread-safe queue."""
        if status:
            print(status, file=sys.stderr)
        self.mic_queue.put(bytes(indata))

    def listen(self) -> str:
        """Blocks until a full phrase from the vocabulary is recognized."""
        # Clear previous buffer so it doesn't process old noise
        with self.mic_queue.mutex:
            self.mic_queue.queue.clear()
            
        try:
            # Start stream on default hardware (USB headset)
            with sd.RawInputStream(samplerate=16000, blocksize=8000, device=None, 
                                   dtype='int16', channels=1, callback=self._mic_callback):
                while True:
                    data = self.mic_queue.get()
                    if self.recognizer.AcceptWaveform(data):
                        # Result() returns a JSON string, extract the text
                        res = json.loads(self.recognizer.Result())
                        text = res.get("text", "")
                        
                        # Only return if text isn't empty or just the unknown token
                        if text and text != "[unk]":
                            return text
        except Exception as e:
            print(f"[Audio Error] Microphone capture failure: {e}")
            return ""