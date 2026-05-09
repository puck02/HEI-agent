#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path
from PIL import Image, ImageOps


def main() -> int:
    if len(sys.argv) != 3:
        print('usage: make-gif.py FRAME_DIR OUT_GIF')
        return 2
    frame_dir = Path(sys.argv[1])
    out_gif = Path(sys.argv[2])
    frames = sorted(frame_dir.glob('*.png'))
    if not frames:
        raise SystemExit('no frames found')

    images = []
    for p in frames:
        img = Image.open(p).convert('RGB')
        # Keep README GIF reasonably small while preserving mobile UI readability.
        img = ImageOps.contain(img, (390, 780), method=Image.Resampling.LANCZOS)
        # Adaptive palette per frame keeps colors decent and file size manageable.
        img = img.convert('P', palette=Image.Palette.ADAPTIVE, colors=128)
        images.append(img)

    durations = []
    for p in frames:
        name = p.name
        if 'welcome' in name:
            durations.append(120)
        elif 'typing' in name:
            durations.append(70)
        elif 'typed' in name:
            durations.append(120)
        elif 'loading' in name:
            durations.append(140)
        else:
            durations.append(180)

    out_gif.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        out_gif,
        save_all=True,
        append_images=images[1:],
        duration=durations,
        loop=0,
        optimize=True,
        disposal=2,
    )
    print(out_gif)
    print('frames', len(images), 'bytes', out_gif.stat().st_size)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
