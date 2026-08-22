# Every constructor the notes reader can produce

This fixture exists so `docs/record-grammar.md` is verified rather than
believed. It is not prose anybody needs to read; it is one instance of each
block constructor `commonmark_x-smart-attributes-fancy_lists` emits.

Four constructors are **not** here because no reader we use produces them:
`LineBlock`, `Figure`, `Table` and `DefinitionList` live in
`tests/fixtures/ast/unreachable-constructors.json` and arrive by `--as=pandoc-ast`.

A plain paragraph, which is `Para`.

> A block quote, which is `BlockQuote`, and holds a paragraph of its own.

```python
# a fenced code block, which is CodeBlock, with an info string
x = 1
```

<div class="raw-html">
<p>A raw HTML block, which is RawBlock.</p>
</div>

::: aside
A fenced div, which is `Div`, and holds this paragraph.
:::

## A level-two heading, which is `Header`

- a tight bullet item, which collapses into `ListItem` carrying `wrap: Plain`
- a second item, so the list has a `next` chain

1. a tight ordered item
2. a second ordered item

- a loose bullet item, which carries `wrap: Para`

- a second loose item, so the looseness is unambiguous

- an item that holds two blocks, so `ListItem` takes the uncollapsed form

  and this is its second paragraph

---
