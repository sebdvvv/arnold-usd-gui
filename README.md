
# arnold-usd-gui

Minimal dark UI to **kick Arnold renders from USD**.


<img width="608" height="666" alt="2026-11-12_18-43-05" src="https://github.com/user-attachments/assets/2886f812-29cc-4572-8641-111c886550cb" />


- Drop a `.usd`, `.usda`, or `.usdc` file.
- Optionally layer a RenderSettings USD above it.
- Pick a camera and an output path or let the app defaults.
- Press **Kick Arnold Render**. The tool writes a temporary USD (scene + RenderSettings + your edits) and runs `kick` on it.

## Requirements

- **Python 3.10+**
- **PySide6** (Qt 6). PySide2 still works if it is already installed.
- **OpenUSD** (`pxr`) on `PYTHONPATH`
- **Arnold** `kick` (`kick.exe` on Windows)

OpenUSD is not installed by this project. Use the USD build that matches your Arnold USD plugin.

## Run

**Windows** — double-click `arnold-usd-gui.bat` (uses `pythonw`, so no console). From a terminal:

```bat
arnold-usd-gui.bat
arnold-usd-gui.bat scene.usda
```

**Linux / macOS**

```bash
chmod +x arnold-usd-gui
./arnold-usd-gui
./arnold-usd-gui scene.usda
```

From a clone without installing the package, the launchers above set `PYTHONPATH` to `src`. To do that yourself:

```bat
set PYTHONPATH=src
python -m arnold_usd_gui
```

## What the button does

Kick is resolved in this order:

1. The executable saved in **Configuration → Arnold Paths**
2. The ARNOLD_ROOT saved there → `ARNOLD_ROOT/bin/kick`
3. The `ARNOLD_ROOT` environment variable, same layout
4. A directory already on `PATH` whose path contains `arnold` and that contains `kick` or `bin/kick`

The GUI builds one temporary `.usda`:

1. Your edits (camera, output, Arnold options, `renderSettingsPrimPath`) — strongest
2. The RenderSettings USD, when **Use a RenderSettings USD** is on
3. The dropped scene — weakest

Frame range, up axis, meters per unit, and the default prim are copied from the scene onto that file so Arnold sees them. `kick` is then started once per frame:

```text
kick -i <temp.usda> -o <output> -frame <n> -c </camera> <custom flags>
```

Custom flags are appended, so a later `-set` can override a value. The field starts as `-dw -dp -nokeypress -v 2` (batch, no window, no keypress). **Show RenderView** is on by default. It drops `-dw` and `-dp`, and on Windows starts kick in its own console so Arnold's RenderView opens the same way it does from cmd. Kick's log is copied into the window. With the box off, `-dw` is kept and the render stays in batch mode.

## Frames

- **Still** renders the Frame value.
- **Animated** renders Start / End / Step when Frames is empty.
- Frames accepts commas and ranges: `1, 24, 48` or `1-48` or `10-8`.
- **FML** fills Frames with the first, middle, and last frame of Start–End.

An animated output without a `#` token gets `.####` before the extension (`shot.exr` → `shot.####.exr` → `shot.0001.exr`).

## Arnold options

Authored attributes are listed when they are:

- `arnold:*` on a `RenderSettings` prim, or
- any attribute on an `ArnoldOptions` prim

Edits are written into the temporary USD. **Help → Arnold options** lists kick flags and the common Arnold parameters (`AA_samples`, ray depths, textures, ignore flags). On RenderSettings the same name is stored as `arnold:AA_samples`.

## Save

**File → Save Render USD** writes the same composed stage next to the source:

`shot.usdc` → `shot_render.usdc`

The extension is unchanged. Sublayer paths are relative when the files share a drive.

## License

MIT — see [LICENSE](LICENSE).
