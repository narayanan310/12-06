"""
domain_resolver.py
Production domain ontology layer.
"""

HOT = ["greenhouse","boiling","roasting","sweltering","melting","sauna"]
COLD = ["freezing","icebox","arctic","antarctica","shivering"]
FRESH = ["stuffy","claustrophobic","fresh air","breeze"]

def resolve(text:str):
    t=text.lower()
    if any(w in t for w in HOT):
        return {"intent":"HOT"}
    if any(w in t for w in COLD):
        return {"intent":"COLD"}
    if any(w in t for w in FRESH):
        return {"intent":"FRESH_AIR"}
    return None
