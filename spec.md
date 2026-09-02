# om4Themes
This will be a filterable webpage that displays themes available for Omarchy, then filter them based on the depth of compatibility with Omarchy 4. It will target the official source of themes, then use a defined method of grading their compatibility. 

### Project Features
- hosted as a github pages site
- built via a github workflow that runs weekly
- shows the themes, their preview pictures, and links to github
- allows filtering by compatibility, creator, dark, light, and official


### Compatibility 
| Level | Label                 | Meaning                                                       | Machine-testable rule                                                                                                  |
| ----- | --------------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| **0** | ❌ Incompatible        | Cannot be converted/rendered correctly on Quattro             | No usable `colors.toml`, no convertible legacy palette, or theme fundamentally depends on removed Omarchy 3 components |
| **1** | 🟠 Legacy Compatible  | Works through Omarchy's backwards-compatibility machinery     | No native Quattro palette, but Omarchy can derive `colors.toml` from legacy `alacritty.toml` / aliases                 |
| **2** | 🟡 Quattro Compatible | Uses the current basic theme system and should work correctly | Has valid `colors.toml`; official Quattro template renderer can generate required files                                |
| **3** | 🟢 Quattro Native     | Written for Omarchy 4 rather than merely tolerated by it      | Current semantic palette/conventions, no required Waybar/`.conf`/old-state dependencies, current theme mechanisms used |
| **4** | 💚 Quattro Verified   | Actually tested against the target Quattro release            | Your CI installs/sanitizes/renders the theme using the official Omarchy code and completes without errors              |


Level 0: Incompatible

Examples of strong failure indicators:

no colors.toml
no legacy alacritty.toml from which Omarchy can extract colors
theme requires Waybar CSS to function
theme requires Walker, Mako, SwayOSD or hyprlock customization as its primary implementation
depends on hyprland.conf being loaded
scripts/templates require ~/.config/omarchy/current/theme
assumes the pre-Quattro ~/.local/share/omarchy layout

Quattro replaced Waybar and several separate UI programs with Quickshell, switched Hyprland configuration from .conf to Lua, and moved generated theme state to ~/.local/state/omarchy/current.

Presence of one old file should probably produce a warning, rather than an automatic Level 0. A repo may simply contain stale junk.

Level 1: Legacy Compatible

This is an important category because Omarchy deliberately supports it.

Quattro's theme-setting process can generate a colors.toml from an older alacritty.toml if necessary. Omarchy's release notes explicitly mention broader compatibility with old themes through palette extraction.

So:

colors.toml       ❌
alacritty.toml    ✅ usable palette
official conversion succeeds

→ Legacy Compatible

The distinction I'd make on the webpage:

Works on Omarchy 4 using its legacy compatibility layer. Custom pre-Quattro styling may not carry over.

This is where a surprising number of old themes will probably land.

Level 2: Quattro Compatible

The theme has a native colors.toml and Omarchy can generate the Quattro shell/application themes from it.

colors.toml is now the core source of truth. It drives terminals, Hyprland, Chromium, btop, editors and the Quickshell desktop shell.

Rather than hardcoding every required field forever, I'd have your analyzer do both:

Static:
parse colors.toml
validate known color values

Dynamic:
feed theme into the pinned Omarchy theme renderer
verify all default/themed/*.tpl templates render

That is much more future-proof than maintaining your own idea of what Omarchy requires.

You can still report palette completeness separately:

mode
accent
selection
muted

background
dark_background
darker_background
lighter_background

foreground
dark_foreground
light_foreground
bright_foreground

red
green
yellow
blue
magenta
cyan

bright_red
bright_green
bright_yellow
bright_blue
bright_magenta
bright_cyan

Omarchy also preserves legacy aliases internally, so missing one canonical semantic field does not necessarily mean the theme is broken.

Level 3: Quattro Native

This answers a slightly different question:

"Was this theme actually designed around Omarchy 4?"

I would require:

valid colors.toml
+
Quattro renderer succeeds
+
no required old ~/.config/omarchy/current paths
+
no required Waybar/Walker/Mako/etc. configuration
+
no required Hyprland .conf overrides
+
current Quattro conventions used where customization exists

A theme doesn't have to have shell.toml to qualify. That's important.

Omarchy intentionally lets a theme consist primarily of colors.toml; current templates generate the rest.

But if it wants to customize things beyond colors, Quattro gives it native mechanisms such as:

shell.toml
shell.menu.toml
shell.notifications.toml
shell.lock.toml
other shell.<section>.toml
semantic border/gradient definitions
spacing/font/bar tokens

The Quickshell theme API explicitly exposes corner radius, alpha/fill values, border widths, gradients and per-surface styling.

So this is where our old "will the rounded corners/transparency survive?" question gets much easier to answer.

Level 4: Quattro Verified

This is the gold sticker.

Your GitHub Action actually runs the theme through the Omarchy code for the version you're targeting.

For example:

Theme: rose-pine-custom
Compatibility: Quattro Verified
Tested against: Omarchy 4.0.1
Commit: abc123...
Tested: 2026-09-02

Omarchy's own test suite already tests theme rendering, legacy palettes, template aliases, section overrides, gradients and theme-state migration. That gives your coding agent an excellent blueprint for creating your validator.

You could eventually have two verification strengths:

Headless Verified → renderer/install pipeline succeeds.

Visual Verified → disposable Omarchy VM boots, sets theme, screenshots shell.

I wouldn't make those separate compatibility levels initially. Just badges.

Feature badges

This is where I'd put everything we talked about previously.

A theme could display:

🟢 Quattro Native

and underneath:

Transparency Rounded UI Custom Borders Gradient Borders Light Mode Custom Shell Unlock Theme Icons Wallpapers

This separation is really useful because a completely flat theme with no transparency can be perfectly Quattro-native, while an elaborate transparent theme could merely be Legacy Compatible.

For example, current Quattro explicitly exposes fill alpha, border alpha, border widths/gradients and a shell-wide cornerRadius system.

Your detector could therefore look for things such as:

shell.toml / shell.*.toml

*-fill-alpha
*-border-alpha
corner-related settings
rgba(...)
border gradients
mode = "light"
icons.theme
unlock.png
preview-unlock.png
backgrounds/
preview.png

That would resurrect our old visual audit, but in a much cleaner form.


### Additional Notes
One particularly important design decision

I'd version the analyzer rules.

Don't store:

"quattroCompatible": true

Store something closer to:

{
  "compatibility": {
    "family": "omarchy-4",
    "level": 3,
    "label": "quattro-native",
    "testedAgainst": "v4.0.1",
    "omarchyCommit": "...",
    "analyzedAt": "..."
  }
}

The reason is already visible only a few weeks into Quattro. A post-release security change modified what files themes installed from remote Git repos are allowed to retain, with .lua, terminal configs and vscode.json being stripped and regenerated from colors.toml.

So "compatible with Omarchy 4" is a moving target, albeit a slowly moving one.

How I picture the eventual pipeline

The architecture almost writes itself:

omarchythemes.com
        ↓
discover theme GitHub URLs
        ↓
GitHub API / git clone
        ↓
static analyzer
 ├─ colors.toml
 ├─ old paths/components
 ├─ shell.toml
 ├─ legacy files
 └─ feature detection
        ↓
official Omarchy renderer
        ↓
compatibility level + badges
        ↓
JSON database
        ↓
static website
        ↓
GitHub Pages

Then GitHub Actions can rerun it daily/weekly, and each result can even say why it got its rating:

🟢 Quattro Native
Native colors.toml ✓
Semantic palette ✓
Quattro renderer ✓
No legacy Waybar dependency ✓
No old state-path references ✓
Custom Quickshell styling ✓

Features: Transparency · Rounded UI · Gradients · 6 Wallpapers

That would be considerably more useful than simply recreating omarchythemes.com. It becomes a little theme compatibility observatory 🔭.

If we continue with this project, the next useful step would be to turn the rubric above into an exact machine-readable detection specification, including filenames, regexes, positive/negative weights, and the JSON output schema your coding model should implement.



### Reference Websites

| Source                                                                                                                                                                 | Why the agent needs it                                                                                                                                                               |
| ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Omarchy `docs/theming.md`** [Quattro theming documentation](https://github.com/omacom/omarchy/blob/quattro/docs/theming.md?utm_source=chatgpt.com)                   | **Primary source.** Explains `colors.toml`, template generation, semantic colors, gradients, `shell.toml`, overrides and theme activation                                            |
| **Making Your Own Theme** [Official theme authoring guide](https://github.com/omacom/omarchy/blob/quattro/manual/43-making-your-own-theme.md?utm_source=chatgpt.com)   | What a modern distributed theme is actually expected to contain, including light mode, icons, unlock screens and third-party repo behavior                                           |
| **Quattro shell docs** [Omarchy shell documentation](https://github.com/omacom/omarchy/blob/quattro/docs/omarchy-shell.md?utm_source=chatgpt.com)                      | Essential for detecting whether transparency, borders, rounded corners, spacing, typography, etc. have been migrated properly                                                        |
| **Official themes** [Omarchy built-in themes](https://github.com/omacom/omarchy/tree/quattro/themes?utm_source=chatgpt.com)                                            | Your canonical positive fixtures. The analyzer should compare community repos against the structure of real Omarchy themes                                                           |
| **Default generated templates** [Omarchy themed templates](https://github.com/omacom/omarchy/tree/quattro/default/themed?utm_source=chatgpt.com)                       | Perhaps the most useful **code** source. Shows exactly what Omarchy tries to generate from a theme palette                                                                           |
| **Theme tests** [Omarchy CLI/theme tests](https://github.com/omacom/omarchy/blob/quattro/test/cli?utm_source=chatgpt.com)                                              | Fantastic source for your local model. Contains executable definitions of legacy palette support, semantic aliases, gradients and section merging. ([GitHub][1])                     |
| **Testing documentation** [Omarchy testing documentation](https://github.com/omacom/omarchy/blob/quattro/docs/testing.md?utm_source=chatgpt.com)                       | Explains which tests own the theme pipeline and how headless testing is done. ([GitHub][2])                                                                                          |
| **Quattro PR #6231** [Original Omarchy Quattro pull request](https://github.com/omacom/omarchy/pull/6231?utm_source=chatgpt.com)                                       | Best historical document explaining what actually disappeared or changed between Omarchy 3 and 4. ([GitHub][3])                                                                      |
| **Omarchy 4.0 release** [Omarchy releases](https://github.com/omacom/omarchy/releases?utm_source=chatgpt.com)                                                          | Defines the stable Quattro feature set and gives you commits/tags to pin your rule engine to. v4.0.0 was released August 14, 2026 at commit `f002044`. ([GitHub][4])                 |
| **`AGENTS.md`** [Omarchy agent development notes](https://github.com/omacom/omarchy/blob/quattro/AGENTS.md?utm_source=chatgpt.com)                                     | Surprisingly useful distilled description of current config structure, theme templates and tests. ([GitHub][5])                                                                      |
| **Current Hyprland loader** [Quattro Hyprland loader](https://github.com/omacom/omarchy/blob/quattro/default/hypr/omarchy.lua?utm_source=chatgpt.com)                  | Lets the analyzer understand the `.conf` → Lua transition and how current theme overrides are loaded. ([GitHub][6])                                                                  |
| **Quattro old-path breakage discussion #7383** [Quattro theme-hook incompatibility example](https://github.com/omacom/omarchy/discussions/7383?utm_source=chatgpt.com) | Excellent negative fixture. Shows exactly how old `~/.config/omarchy/current` assumptions break under Quattro. ([GitHub][7])                                                         |
| **Issue #7942** [Repo-installed theme sanitization discussion](https://github.com/omacom/omarchy/issues/7942?utm_source=chatgpt.com)                                   | Important for community themes specifically. Current Omarchy sanitizes git-installed themes and regenerates some files rather than trusting executable/config content. ([GitHub][8]) |

[1]: https://github.com/basecamp/omarchy/blob/quattro/test/cli?utm_source=chatgpt.com "omarchy/test/cli at quattro · basecamp/omarchy · GitHub"
[2]: https://github.com/omacom/omarchy/blob/quattro/docs/testing.md?utm_source=chatgpt.com "omarchy/docs/testing.md at quattro · omacom/omarchy · GitHub"
[3]: https://github.com/omacom/omarchy/pull/6231?utm_source=chatgpt.com "Omarchy Quattro by dhh · Pull Request #6231 · omacom/omarchy · GitHub"
[4]: https://github.com/omacom/omarchy/releases?utm_source=chatgpt.com "Releases · omacom/omarchy · GitHub"
[5]: https://github.com/omacom/omarchy/blob/quattro/AGENTS.md?utm_source=chatgpt.com "omarchy/AGENTS.md at quattro · omacom/omarchy · GitHub"
[6]: https://github.com/basecamp/omarchy/blob/quattro/default/hypr/omarchy.lua?utm_source=chatgpt.com "omarchy/default/hypr/omarchy.lua at quattro · basecamp/omarchy · GitHub"
[7]: https://github.com/basecamp/omarchy/discussions/7383?utm_source=chatgpt.com "Omarchy Quattro GTK theming issue. · basecamp omarchy · Discussion #7383 · GitHub"
[8]: https://github.com/basecamp/omarchy/issues/7942?utm_source=chatgpt.com "Let repo-installed themes supply themed/*.tpl template overrides · Issue #7942 · basecamp/omarchy · GitHub"
