-- make_sections.lua — wrap headings in the Div `pandoc.utils.make_sections`
-- already knows how to build, so sectioning is pandoc's rule rather than one
-- compost authors and then has to defend against setext headings, a level-3
-- following a level-1, or a heading inside a block quote.
--
-- `--section-divs` does not reach the JSON writer (it is an HTML writer
-- option only); this Lua filter is the one documented way to get the same
-- shape out of `pandoc -t json`. See docs/roadmap.md, "v0.2.16 — TA:
-- revisions, and structure that means something".
--
-- `numbering = true`: measured against the corpus, this is what moves a
-- heading's own identifier onto the wrapping Div and leaves a `number` key
-- behind on both — the "two facts" `src/records.py:hoist` depends on. Every
-- markdown-reading path in `src/` applies this filter identically
-- (`src/markdown.py`'s `_ast_of_text` and `ast_of_file`, its one seam) —
-- guarantee 6 is that no base ever holds two document shapes.
function Pandoc(doc)
  doc.blocks = pandoc.utils.make_sections(true, nil, doc.blocks)
  return doc
end
