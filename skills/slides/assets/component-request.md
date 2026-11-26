# slides: component request `${name}`

- **Kind:** ${kind}
- **Catalog section:** ${section}
- **Purpose:** ${purpose}
- **Use when:** TODO
- **Don't use when:** TODO

## Sample markup

Generated from the slide's structure. Every text is `Sample text` and every icon is empty.

```html
${markup}
```

## CSS

Design tokens only: no literal colour, font, image or quoted text.

```css
${css}
```

## For whoever canonizes this

- Keep the name `${target}`: a deck swaps its local block for the catalog block by that name.
- Keep the class names the sample markup uses; normalise the other names and tokens.
- Add the CSS to the catalog section above as an anchored block, with a worked example; a new component also needs its id, purpose and use-when lines.
- Bump the version of a component you change, in its id line and in each of its anchors.
- Update the chooser table.
- Regenerate the index with `build_catalog.py`.
