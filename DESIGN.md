# Reza Design Context

Reza documentation should feel like a professional developer tool: dark, fast, readable, and task-focused.

Visual direction:

- Dark theme by default using local CSS variables and system fonts.
- No remote font requests.
- No remote icon CDNs.
- Use local tool SVG assets for coding agents and editors.
- Keep card radius at 8px or less for docs surfaces.
- Avoid gradient text, decorative blur shapes, glass panels, and marketing-heavy hero composition.
- Use compact command blocks, restrained borders, and clear metadata.

Typography:

- UI font: system sans stack.
- Code font: system mono stack.
- Use fixed responsive breakpoints, not viewport-scaled font sizes.
- Keep line length readable in docs, around 70 to 76 characters.

Performance:

- Prefer static assets in `public/`.
- Preload the most visible icons and logo.
- Keep documentation pages self-contained and cache-friendly.

Interaction:

- Buttons should include icons when they trigger commands or navigation.
- Copy buttons should use familiar copy/check icons.
- Search and navigation should prioritize scannability over decoration.
