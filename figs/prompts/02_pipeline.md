# Image 2 — RAGtrap pipeline (icon infographic)

- **Save the PNG as:** `paper/figs/pipeline_ragtrap.png`
- **Aspect ratio:** 16:9
- **Where it goes:** the "Design" section (an icon-rich alternative to the
  existing vector diagram)
- **Background the AI needs:** documents are split into small text "chunks"; a
  "gate" inspects each chunk as it enters a searchable store that an AI assistant
  queries later.
- **Note:** carries short labels; if garbled, regenerate or fix text in an editor.

```prompt
Flat vector infographic, horizontal left-to-right pipeline on a pure white
background, clean academic style, thin monoline icons joined by thin arrows with
small triangular arrowheads.
STAGE 1 (far left): an icon of several stacked documents, one tinted faintly red
(an untrusted source that may be poisoned); caption: "Untrusted sources".
ARROW into STAGE 2: a gate / checkpoint box containing three tiny sub-icons in a
row — a hash symbol (#), a small detector magnifier, and a wax-seal/key (signing);
caption: "Gate: hash, detect, sign".
ARROW into STAGE 3: a translucent database cylinder with three little index tabs
on its side (a content-hash index, a per-chunk principal index, signed records);
caption: "Vector store + indexes".
ABOVE the cylinder: a chat/question bubble with a double-headed arrow to the
cylinder; caption: "RAG query (unchanged)".
BELOW-LEFT of the cylinder: a magnifying glass box with an arrow pointing INTO the
cylinder, fed from a small "suspect chunk" card on its left; caption:
"Trace-back: O(1) hash lookup".
BELOW-RIGHT of the cylinder: an eraser / batch-delete box with an arrow into the
cylinder removing one red chunk while green chunks remain; caption:
"Revocation: surgical purge".
Layout: top row is the ingest path (sources -> gate -> store) with the query
bubble above the store; bottom row is the recovery path (trace-back and revocation)
feeding the store from below. Palette: deep navy #1F3A5F for lines, icons and
captions; teal #2A9D8F for the gate's seal and the store accent; amber #E9C46A for
the trace-back magnifier; red only on the single poisoned chunk; light gray fills;
white background; rounded corners; subtle shadows; clean sans-serif for short
captions only. 16:9 aspect ratio, evenly spaced, strong flow, generous white
space. Only the short captions named above — no sentences or paragraphs.
```
