// Legacy builder — prefer: python docs/presentation/build_pitch_deck.py
const pptxgen = require("pptxgenjs");
const path = require("path");

const pres = new pptxgen();
pres.layout = "LAYOUT_16x9";
const out = path.join(__dirname, "Friday-Voice-Agent.pptx");

const slide = pres.addSlide();
slide.background = { color: "0A0A0A" };
slide.addText("Use build_pitch_deck.py for the full deck.", {
  x: 0.75,
  y: 3,
  w: 10,
  h: 1,
  fontSize: 24,
  color: "FAFAFA",
  isTextBox: true,
  margin: 0,
});

pres.writeFile({ fileName: out }).then(() => console.log("Wrote", out));
