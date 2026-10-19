# OpenPadDisplay icon

`openpaddisplay.png` is the shared master artwork, generated with the built-in
OpenAI image generation tool on 2026-10-19. The desktop and Android launcher icons
are resized from this same file. Android uses an inset foreground so the mark
fits adaptive launcher masks.

Regenerate the committed sizes with `/usr/bin/python3 scripts/build-icons.py`
from the repository root (development dependency: Pillow). Linux uses the 512px
copy; Android includes legacy density variants and an adaptive icon.

Generation prompt:

> Use case: logo-brand. Create one finished app launcher icon for OpenPadDisplay,
> an application that turns an Android tablet into a second PC monitor over USB.
> A simple modern memorable flat geometric symbol of two connected screens, a
> larger monitor behind and a small tablet overlapping in front, forming one
> coherent compact mark. Deep midnight navy full square background, crisp pale
> ice white and vibrant turquoise screen outlines, a tiny connection detail, no
> text or letters. Front-facing orthographic geometry, generous consistent
> rounded corners, precise uniform thick strokes, visually balanced center
> composition, extremely legible at 32px. No perspective, no realistic device
> rendering, no shadows, no reflections, no gradients, no decorative dots, no
> circuitry, no watermark, no border. Single icon only, edge-to-edge solid dark
> square canvas; main symbol fully inside central 62% of canvas so it remains
> intact under Android adaptive icon masks. Professional polished minimalist
> software identity. Output square image.
