# iCal Day View (PySide6)

**NOTE ADD A uploads folder, i don't think i coded it to make one

This repository contains a PySide6-based day-view calendar app (`ical.py`) and a couple of fixed copies that ensure the day view opens **centered on the current time** when the window appears.

Total time per tag

> toggle, Magnet emoji, lets you snap to current time or nearest event block, it also snaps time in blocks. also good for laying out a bunch of blocks at a time.

> toggle, Hour Glass lets you snap in increments of Time Size.

>The Blue, white square when enabled lets you box select a group of time. you can then drag events around.

>The white note icon shows history of actions which should be able to revert from history.  Ctrl+Z, and Ctrl+Y windows undo, redo. command+z, Shift+command+Z(Mac)

>right clicking edit. brings up edit event, this is where you can add titles, tags, change color. add images (**NOTE ADD A uploads folder, i don't think i coded it to make one) adjust time. notify(only tested on mac, I need to work on this for windows?), you can also repeat or make it always an event that happens.

>right click lock makes it so you can't delete or move until unlocked.

## Files you'll find here
- `ical.py` — original script you provided (backup before modifications).
- `ical_fixed_full.py` — full copy with robust centering fixes applied (recommended to test).
- `ical_after.py` — alternate modified copy also intended to produce the “after” behavior.
- `ical_original_backup_for_fix.py` — backup of the original made during edits.
- `requirements.txt` — third-party dependencies (`PySide6`).
- `README.md` — this file.

> All files referenced above are in the same folder. Adjust paths if you move files to another directory.

---

## Requirements
- **Python 3.8 or newer** (3.10 / 3.11 recommended).
- `pip` (comes with most Python installs).
- The GUI uses **PySide6** (Qt for Python).

The required third-party packages are already listed in `requirements.txt` (currently contains `PySide6`).

---
**NOTE ADD A uploads folder, i don't think i coded it to make one

## Quick start (Unix / macOS)
```bash
# create & activate a virtual environment (recommended)
python -m venv venv
source venv/bin/activate

# update pip and install deps
python -m pip install --upgrade pip
pip install -r requirements.txt

# run the fixed copy
python ical_fixed_full.py
```
If you prefer to test the alternate version:
```bash
python ical_after.py
```

## Quick start (Windows PowerShell)
```powershell
python -m venv venv
venv\Scripts\Activate.ps1

python -m pip install --upgrade pip
pip install -r requirements.txt

python ical_fixed_full.py
```

## Replace the original safely
Make a backup first, then move the fixed file into place:
```bash
cp ical.py ical_backup.py
mv ical_fixed_full.py ical.py
# or (Windows)
rename ical.py ical_backup.py
move ical_fixed_full.py ical.py
```

## What I changed (short summary)
To reliably center the day view on the current time after the window opens, the fixed versions include three complementary strategies:
1. Connect to the day-view `QScrollBar.rangeChanged` event and center once the scrollbar range is known (disconnects after first use).  
2. Add a `showEvent` override that calls `center_on_current_time` when the window is shown (and schedules a short delayed retry).  
3. Add short `QTimer.singleShot(...)` fallback delays (e.g., 200–250 ms) to cover timing quirks across platforms/window managers.

This combination is robust across typical platforms and matches the “after” screenshot behavior you showed.

## Troubleshooting
- **ModuleNotFoundError: No module named 'PySide6'**  
  Run `pip install PySide6` (or ensure your virtualenv is activated and `pip install -r requirements.txt` is used).

- **Blank/white window or scaling issues**  
  Try resizing or maximizing the window. On some platforms desktop scaling and Qt style/plugins can affect layout; updating PySide6 to a more recent patch release may help.

- **App still not centering**  
  - Make sure you're running one of the modified files (`ical_fixed_full.py` or `ical_after.py`).  
  - Try running while the window manager is not auto-tiling or adjusting windows (i.e., test in a normal floating window).  
  - If you want, paste a screenshot or describe the difference and I’ll tweak the timing/centering parameters further.

## Packaging (optional)
To create a single executable you can use `PyInstaller`:
```bash
pip install pyinstaller
pyinstaller --onefile ical_fixed_full.py
```
Note: bundling Qt apps can require extra hooks; check PyInstaller docs if resources/plugins are missing at runtime.

## Development notes
- The code expects there to be a `self.scroll_area` attribute on the main window (a `QScrollArea`) with a vertical scrollbar. If you refactor the UI, keep the centering hooks connected to the actual scrollbar object.

## License & contact
No license file included by default. If you want an explicit license (MIT, Apache 2.0, etc.), tell me and I’ll create one. If you want additional readme content (contribution steps, issue template, screenshots, or a GIF), I can add that too.

---
*Generated automatically from the copy of `ical.py` you provided.*
