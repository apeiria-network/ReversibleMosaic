"""List every recipe URL/filename that p4a will download for our probe."""

from __future__ import annotations

import os
from pythonforandroid.build import Context
from pythonforandroid.recipe import Recipe

RECIPES = [
    "hostpython3",
    "jpeg",
    "libffi",
    "libwebp",
    "openssl",
    "png",
    "sdl2_image",
    "sdl2_mixer",
    "sdl2_ttf",
    "sqlite3",
    "python3",
    "sdl2",
    "libthorvg",
    "pyjnius",
    "setuptools",
    "android",
    "kivy",
]


def main() -> None:
    ctx = Context()
    ctx.setup_dirs(os.path.expanduser("~/.buildozer/android/platform"))
    for name in RECIPES:
        try:
            recipe = Recipe.get_recipe(name, ctx)
            version = getattr(recipe, "version", None)
            url = getattr(recipe, "url", None)
            versioned = None
            try:
                versioned = recipe.versioned_url
            except Exception as exc:  # noqa: BLE001
                versioned = f"ERR:{exc}"
            print(f"{name}\t{version}\t{url}\t{versioned}")
        except Exception as exc:  # noqa: BLE001
            print(f"{name}\tERR\t{exc}")


if __name__ == "__main__":
    main()
