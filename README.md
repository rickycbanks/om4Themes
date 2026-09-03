# 🔭 om4Themes

![Build](https://img.shields.io/github/actions/workflow/status/rickycbanks/om4Themes/build.yml?branch=main&label=build)
![Pages](https://img.shields.io/github/deployments/rickycbanks/om4Themes/github-pages?label=pages)
![Themes graded](https://img.shields.io/badge/dynamic/json?url=https%3A%2F%2Frickycbanks.github.io%2Fom4Themes%2Fdata%2Fthemes.json&query=%24.run.analyzed&label=themes%20graded&color=blueviolet)

**Last full build:** 2026-09-03 <!-- last-build-date -->

**Live site → https://rickycbanks.github.io/om4Themes/**

om4Themes is a **compatibility observatory for [Omarchy](https://omarchy.org) 4 ("Quattro") themes**. Every week, every Omarchy theme discoverable on GitHub is put through Omarchy's own theming pipeline — installed, sanitized, and rendered exactly as your system would — and the results are published as a filterable gallery with evidence behind every grade.

## Why not just omarchythemes.com?

[omarchythemes.com](https://omarchythemes.com) is a lovely gallery: ~250 themes, screenshots, links. What it can't tell you is whether a theme actually works on *today's* Omarchy. Quattro changed the theming model substantially, and much of the ecosystem predates it. om4Themes is built for that question:

- **Grades earned, not guessed** — every rating comes from running the theme through the real Omarchy renderer at a pinned release.
- **Evidence for every verdict** — each card opens to show its per-check reasoning ("Native colors.toml ✓ · Quattro renderer ✓ · No legacy Waybar dependency ✓").
- **Grades that age honestly** — every result records the Omarchy version, commit, and date it was tested against.
- **Feature badges** — transparency, rounded UI, gradient borders, light mode, custom shell, wallpapers, and more, detected independently of compatibility.
- **Machine-readable** — the full dataset is public JSON at [`/data/themes.json`](https://rickycbanks.github.io/om4Themes/data/themes.json).
- **Zero-touch** — re-runs weekly; new themes appear automatically.

The galleries are complementary: browse screenshots there, check compatibility here.

## How ratings work

Themes are judged against Omarchy 4 (Quattro) using Omarchy's own machinery — the same stage → sanitize → render pipeline that runs when you install a theme — plus static analysis of what the theme actually depends on.

| Rating | What it means |
|---|---|
| ❌ **Incompatible** | Nothing installable found — no usable palette (common for collection/dotfile repos, or pre-Quattro themes whose colors can't be extracted) |
| 🟠 **Legacy Compatible** | Works through Omarchy 4's backwards-compatibility layer (palette extracted from an older alacritty.toml). Custom pre-Quattro styling won't carry over |
| 🟡 **Quattro Compatible** | Native colors.toml renders cleanly through the official pipeline |
| 🟢 **Quattro Native** | Renders cleanly *and* shows no dependency on removed Omarchy 3 components (Waybar, Walker, Mako, SwayOSD, hyprlock, old state paths) — designed around current Quattro |
| 💚 **Quattro Verified** | A full install simulation — staging, sanitization, and rendering against a specific Omarchy release — completed cleanly by this project's CI. The gold sticker: tested, not just analyzed |

Two honest notes:

- A theme that looks fine in its repo can grade lower if it relies on files Omarchy strips during install (custom Lua, terminal configs) — grading reflects *as-installed* reality.
- Incompatibility is a compatibility statement, not a quality judgment. Many "Incompatible" repos are theme *collections* or dotfile kits, not single installable themes.

## Credits

- **[Omarchy](https://omarchy.org)** — the OS this observatory watches, and the theming pipeline every grade is tested against.
- **[omarchythemes.com](https://omarchythemes.com)** — the original theme gallery and community gathering point.
- **Every theme creator** linked from this site — your work is what makes the ecosystem worth observing.

## Disclaimer

om4Themes is an independent, unofficial project. All themes are owned by their respective creators and are linked to their original repositories. This project neither hosts nor distributes theme code and is not responsible for the content, quality, or safety of any theme — installing themes is at your own risk. Compatibility grades are automated, best-effort checks against a pinned Omarchy release as of the analysis date, not endorsements.

## License

Code in this repository is MIT — see LICENSE. Theme artwork and code belong to their creators.
