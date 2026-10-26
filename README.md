# Asset Check

A read-only command-line preflight for game-asset folders. Find exact duplicates, misleading image extensions, corrupt images, oversized textures and filenames that may cause cross-platform problems. Get a terminal summary, JSON for automation, or a self-contained HTML report.

**No accounts, uploads, telemetry or paid service. No delete, rename, move or repair operation.** The tool reads source assets and writes a report only when you explicitly choose a new output path outside the scanned folder.

## Quick start

Python 3.10+ and Pillow are required:

```sh
python -m pip install -r requirements.txt
python asset_check.py path/to/assets
```

Save reports outside the asset folder:

```sh
python asset_check.py path/to/assets --format json --output asset-report.json
python asset_check.py path/to/assets --format html --output asset-report.html
```

Existing reports are never overwritten. Choose a new name for another run. Output directories must already exist. JSON and HTML contain relative filenames, so review them before sharing: project filenames can still be sensitive.

## Checks

| Check | What it means |
| --- | --- |
| Byte duplicates | Same size and SHA-256. Files may be intentionally referenced in more than one place. |
| Pixel duplicates, optional | Same dimensions and exactly matching decoded RGBA pixels, even if PNG metadata differs. Color profiles are not compared; this is not fuzzy/perceptual matching. |
| Image extension mismatch | For example, JPEG content named `.png`. Renaming is not format conversion. |
| Image integrity | Verify the supported image, then decode its first frame within the pixel budget. Animated images are not fully audited frame by frame. |
| Oversized textures | Above your configurable review threshold. Default 2048px per side is a policy choice, not a universal Roblox/Unity/Godot limit. |
| Nonportable filenames | Reserved Windows names, incompatible characters, trailing dots/spaces. Normal spaces and Unicode are allowed. |
| Case collisions | Paths that differ only by case may collide on case-insensitive systems. |
| Power-of-two, optional | Use only if your project requires it; modern projects do not universally need power-of-two dimensions. |

Other regular files are hashed for byte duplicates. Supported image formats depend on Pillow: PNG, JPEG, WebP, GIF, BMP, TIFF, TGA, DDS, ICO and PSD. Recognized image signatures with a different or missing extension are also inspected. Unknown formats are not claimed to be validated.

## Options

```sh
python asset_check.py path/to/assets --pixel-duplicates --max-dimension 4096
python asset_check.py path/to/assets --require-power-of-two --fail-on warning
```

- `--max-dimension 2048`: review threshold for image sides.
- `--max-file-mb 256`: skip hashing/decoding larger files.
- `--max-files 20000`: stop after this many regular files.
- `--max-image-mp 32`: decode at most about 32 million pixels per image.
- `--pixel-duplicates`: enable decoded RGBA comparison; costs more memory/time.
- `--require-power-of-two`: opt-in project policy.
- `--format text|json|html`: defaults to terminal text.
- `--output NEW_PATH`: optional report outside the source folder; defaults to stdout.
- `--fail-on error|warning|never`: controls findings-based exit status.

Symlinks, junctions and other reparse points are skipped. Generated/version-control folders `.git`, `.godot`, `node_modules`, `.venv`, `__pycache__`, `Library`, `Temp` and `obj` are ignored (case-insensitive). Root symlinks/junctions are refused. Skips are listed in the report. Resource limits and unreadable files make the report incomplete; intentional ignored folders do not.

Avoid changing files while scanning. A size/mtime change detected during hashing is reported and excluded from duplicate matching. This is a normal local audit, not an adversarial filesystem snapshot or malware scanner.

## Exit codes / automation

- **0**: completed; no findings at your chosen failure level.
- **1**: completed; findings reached your failure level. Default is errors only.
- **2**: invalid command, write/read failure or incomplete scan. `--fail-on never` does not hide an incomplete scan.

A duplicate/oversized warning alone does not fail the default command. A corrupt image does. A large skipped file is not reported as corrupt: it makes coverage incomplete.

GitHub Actions example for your own project:

```yaml
- run: python -m pip install Pillow
- run: python path/to/asset_check.py assets --fail-on warning
```

## Try a fictional asset folder

```sh
python examples/make_demo.py
python asset_check.py examples/demo --max-dimension 256 --pixel-duplicates
```

The original generated demo intentionally contains a duplicate, a JPEG with a PNG extension, a wide image and a corrupt image. It produces findings and exits **1**. The generator refuses to replace an existing demo folder. No personal or downloaded art is used.

## Test

```sh
python -m unittest discover -s tests -v
```

Tests check that input bytes/mtimes stay unchanged, byte/pixel duplicate behavior, extension/corruption/dimension findings, opt-in policies, case handling, symlink exclusion, resource limits, HTML escaping, report protection and exit codes. Public CI runs on Windows and Linux; platform-specific tests may skip where unsupported.

## Scope and license

This does not determine whether an asset is unused, update engine references, optimize images, inspect mesh geometry, validate licensing, fetch remote URLs, or decide what is safe to delete. Fixes and paid services are not part of this repository. Use an engine-specific tool when you need dependency/reference analysis.

MIT. Source and demo content are original Project ZERO work. Your own assets remain yours. Report bugs with small examples you are allowed to share publicly.
