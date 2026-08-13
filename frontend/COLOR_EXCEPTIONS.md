# Static color exceptions

Application UI colors are defined in `src/index.css` and consumed through semantic
tokens/Tailwind semantic utilities. The following files intentionally retain literal
colors because they are standalone static artwork or browser metadata, not themed UI
components:

- `public/assets/illustrations/study-hero.svg`
- `public/assets/illustrations/search-empty.svg`
- `public/assets/illustrations/document-upload.svg`
- `public/assets/illustrations/peer-collaboration.svg`
- `public/favicon.svg`
- `public/manifest.webmanifest`

The SVG illustrations are self-contained decorative artwork and the favicon is a fixed brand asset;
recoloring them through page CSS would change the supplied artwork and is not needed
for text, controls, or icon contrast. The web manifest's `theme_color` and
`background_color` are browser/PWA metadata, not component styles.

New application UI should not add literal colors to source files. Add an appropriate
semantic token in `src/index.css` instead.
