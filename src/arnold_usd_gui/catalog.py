"""Help text: kick flags and Arnold option parameters."""

from __future__ import annotations

import html

# Flags kick accepts. -i / -o / -frame / -c are filled by the GUI;
# the rest are meant for the custom-flag field. `kick -h` on the
# installed build is the complete list.
KICK_FLAGS: list[tuple[str, str]] = [
    ("-i <file>", "Input scene (.ass, .usd, .usda, .usdc). The GUI passes the temporary USD."),
    ("-o <file>", "Output image. The GUI passes the Output Render path, one file per frame."),
    ("-frame <n>", "Frame to render. The GUI sends one kick per frame."),
    ("-c <camera>", "Camera node. The GUI passes the USD camera prim path."),
    ("-r <w> <h>", "Override the render resolution."),
    ("-v <n>", "Verbosity, 0 (quiet) through 6 (debug). 2 is a typical batch setting."),
    ("-dw", "Disable the display window so kick stays in batch mode."),
    ("-dp", "Disable progressive refinement and render final buckets."),
    ("-nokeypress", "Do not wait for a keypress when the frame finishes."),
    ("-nocrashpopup", "Do not open the crash dialog."),
    ("-t <n>", "Thread count. 0 lets Arnold choose."),
    ("-bs <n>", "Bucket size in pixels."),
    ("-as <n>", "Camera (AA) samples. Overrides options.AA_samples."),
    ("-ds <n>", "Diffuse samples. Overrides options.GI_diffuse_samples."),
    ("-gs <n>", "Specular samples. Overrides options.GI_specular_samples."),
    ("-ss <n>", "Transmission samples. Overrides options.GI_transmission_samples."),
    ("-sss <n>", "Subsurface samples. Overrides options.GI_sss_samples."),
    ("-ls <n>", "Light samples override."),
    ("-vs <n>", "Volume samples. Overrides options.GI_volume_samples."),
    ("-set <node.param> <value>", "Set an Arnold parameter, for example -set options.AA_samples 4."),
    ("-l <logfile>", "Also write the log to a file."),
    ("-device <cpu|gpu>", "Render device."),
    ("-nstdin", "Read the scene from stdin instead of -i."),
    ("-resave <file.ass>", "Write the loaded scene out as an .ass file."),
    ("-sf <n>  -ef <n>  -fs <n>", "Start, end, and step. This GUI loops -frame instead, so these are optional."),
]

# Names as authored on an ArnoldOptions prim. On a RenderSettings prim the
# same parameter is the attribute arnold:<name>.
OPTION_GROUPS: list[tuple[str, list[tuple[str, str, str]]]] = [
    (
        "Sampling",
        [
            ("AA_samples", "int", "Camera (anti-aliasing) samples per pixel."),
            ("AA_samples_max", "int", "Maximum samples when adaptive sampling is on."),
            ("AA_adaptive_threshold", "float", "Adaptive sampling noise threshold."),
            ("enable_adaptive_sampling", "bool", "Stop sampling a pixel once the threshold is reached."),
            ("AA_seed", "int", "Sampling seed. Change it to vary the noise pattern."),
            ("AA_sample_clamp", "float", "Clamp sample intensity before filtering."),
            ("indirect_sample_clamp", "float", "Clamp indirect samples."),
            ("GI_diffuse_samples", "int", "Indirect diffuse samples."),
            ("GI_specular_samples", "int", "Indirect specular samples."),
            ("GI_transmission_samples", "int", "Indirect transmission samples."),
            ("GI_sss_samples", "int", "Subsurface scattering samples."),
            ("GI_volume_samples", "int", "Volume indirect samples."),
        ],
    ),
    (
        "Ray depth",
        [
            ("GI_diffuse_depth", "int", "Indirect diffuse ray depth."),
            ("GI_specular_depth", "int", "Indirect specular ray depth."),
            ("GI_transmission_depth", "int", "Transmission ray depth."),
            ("GI_volume_depth", "int", "Volume ray depth."),
            ("GI_total_depth", "int", "Maximum total ray depth."),
            ("auto_transparency_depth", "int", "How many transparent surfaces a ray continues through."),
            ("low_light_threshold", "float", "Drop lights that contribute less than this amount."),
        ],
    ),
    (
        "System",
        [
            ("threads", "int", "Render threads. 0 uses all available cores."),
            ("bucket_size", "int", "Width and height of a render bucket."),
            ("bucket_scanning", "string", "Bucket order: top, bottom, left, right, random, spiral, hilbert."),
            ("abort_on_error", "bool", "Stop the render when Arnold reports an error."),
            ("abort_on_license_fail", "bool", "Stop instead of watermarking when the license fails."),
            ("render_device", "string", "CPU or GPU."),
            ("gpu_max_texture_resolution", "int", "Maximum texture resolution on GPU."),
        ],
    ),
    (
        "Textures and search paths",
        [
            ("texture_max_open_files", "int", "Maximum number of texture files kept open."),
            ("texture_max_memory_MB", "float", "Texture cache size in megabytes."),
            ("texture_automip", "bool", "Generate missing texture mipmaps."),
            ("texture_autotile", "int", "Auto-tile untiled textures. 0 disables it."),
            ("texture_accept_unmipped", "bool", "Allow textures that have no mipmaps."),
            ("texture_accept_untiled", "bool", "Allow textures that are not tiled."),
            ("texture_searchpath", "string", "Search path for textures."),
            ("procedural_searchpath", "string", "Search path for procedurals."),
            ("plugin_searchpath", "string", "Search path for Arnold plugins."),
            ("asset_searchpath", "string", "Search path used to resolve assets."),
        ],
    ),
    (
        "Ignore flags",
        [
            ("ignore_textures", "bool", "Render without textures."),
            ("ignore_shaders", "bool", "Render without shader networks."),
            ("ignore_atmosphere", "bool", "Skip atmosphere shaders."),
            ("ignore_lights", "bool", "Skip lights."),
            ("ignore_shadows", "bool", "Skip shadow rays."),
            ("ignore_subdivision", "bool", "Skip subdivision."),
            ("ignore_displacement", "bool", "Skip displacement."),
            ("ignore_bump", "bool", "Skip bump mapping."),
            ("ignore_smoothing", "bool", "Skip normal smoothing."),
            ("ignore_motion_blur", "bool", "Render without motion blur."),
            ("ignore_dof", "bool", "Render without depth of field."),
            ("ignore_sss", "bool", "Skip subsurface scattering."),
            ("ignore_operators", "bool", "Skip operator graphs."),
        ],
    ),
]


def help_html(query: str = "") -> str:
    """Dark-theme HTML for Help → Arnold options. ``query`` filters rows."""
    needle = (query or "").strip().lower()
    parts = [
        "<html><body style='color:#e8e8e8; font-family: Segoe UI, sans-serif; font-size:13px;'>",
        "<p>Parameters found on the stage are listed in the Arnold options table. "
        "Edits are written into the temporary USD that kick renders.</p>",
        "<p>On a <b>RenderSettings</b> prim the attribute is "
        "<code>arnold:&lt;name&gt;</code>. On an <b>ArnoldOptions</b> prim the "
        "attribute is <code>&lt;name&gt;</code>. The stage's "
        "<code>renderSettingsPrimPath</code> selects which RenderSettings kick uses. "
        "A RenderSettings USD, when enabled, is layered stronger than the scene.</p>",
        "<p>Kick is resolved from Configuration → Arnold Paths, then "
        "<code>ARNOLD_ROOT/bin</code>, then an Arnold folder already on <code>PATH</code>.</p>",
        "<h3 style='margin-bottom:4px;'>Kick flags</h3>",
        "<p style='color:#aaa;'>Custom flags are appended to the command. "
        "Use quotes around values that contain spaces.</p>",
        "<table cellspacing='0' cellpadding='4' style='border-collapse:collapse;'>",
    ]
    flag_rows = 0
    for flag, desc in KICK_FLAGS:
        if needle and needle not in flag.lower() and needle not in desc.lower():
            continue
        flag_rows += 1
        parts.append(
            "<tr><td style='vertical-align:top; white-space:nowrap; color:#9fd0ff;'>"
            f"<code>{html.escape(flag)}</code></td>"
            f"<td>{html.escape(desc)}</td></tr>"
        )
    if flag_rows == 0:
        parts.append("<tr><td colspan='2' style='color:#999;'>No matching flags.</td></tr>")
    parts.append("</table>")

    for title, rows in OPTION_GROUPS:
        visible = [
            row for row in rows
            if not needle or needle in row[0].lower() or needle in row[1].lower() or needle in row[2].lower()
        ]
        if needle and not visible:
            continue
        parts.append(f"<h3 style='margin-bottom:4px;'>{html.escape(title)}</h3>")
        parts.append("<table cellspacing='0' cellpadding='4' style='border-collapse:collapse;'>")
        for name, type_name, desc in visible:
            parts.append(
                "<tr><td style='vertical-align:top; white-space:nowrap; color:#c8e6c9;'>"
                f"<code>{html.escape(name)}</code></td>"
                f"<td style='color:#bbb;'>{html.escape(type_name)}</td>"
                f"<td>{html.escape(desc)}</td></tr>"
            )
        parts.append("</table>")
    if needle and flag_rows == 0 and not any(
        needle in row[0].lower() or needle in row[1].lower() or needle in row[2].lower()
        for _, rows in OPTION_GROUPS
        for row in rows
    ):
        parts.append("<p style='color:#999;'>Nothing matches that filter.</p>")
    parts.append(
        "<p style='color:#999;'>Bool values accept true/false. "
        "Vectors accept comma-separated numbers, for example <code>1, 0, 0</code>. "
        "A frame token <code>#</code> in the output name is expanded per frame "
        "(<code>####</code> → <code>0001</code>).</p>"
    )
    parts.append("</body></html>")
    return "".join(parts)
