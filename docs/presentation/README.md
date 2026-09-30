# Presentation

## Build (YC-style deck)

```bash
pip install python-pptx
python docs/presentation/build_pitch_deck.py
```

Output: `Friday-Voice-Agent.pptx` (dark slides, problem → solution → diagram → demo).

Narrative source: [../PITCH.md](../PITCH.md).

Optional Node rebuild (legacy): `node build-deck.js` after `npm install pptxgenjs`.
