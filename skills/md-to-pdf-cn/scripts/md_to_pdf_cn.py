#!/usr/bin/env python3
"""Convert Markdown reports to Chinese-friendly PDF via Pandoc and Chrome."""

from __future__ import annotations

import argparse
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse


IMAGE_PROFILES = {
    "compact": {
        "raster_width": "64%",
        "raster_height": "70mm",
        "svg_width": "86%",
        "svg_height": "112mm",
    },
    "normal": {
        "raster_width": "70%",
        "raster_height": "76mm",
        "svg_width": "86%",
        "svg_height": "112mm",
    },
    "large": {
        "raster_width": "75%",
        "raster_height": "86mm",
        "svg_width": "90%",
        "svg_height": "120mm",
    },
}

REMOTE_SCHEMES = {"http", "https", "data", "mailto", "tel", "file"}
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_CSS = SKILL_DIR / "assets" / "pdf-cn-style.css"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Convert Markdown to a Chinese-layout PDF with Pandoc + Chrome."
    )
    parser.add_argument("input", help="Input Markdown file.")
    parser.add_argument("--output", help="Output PDF path. Defaults to input stem + .pdf.")
    parser.add_argument("--workdir", help="Directory for generated Markdown/HTML/check files.")
    parser.add_argument("--css", help="Optional CSS file appended after the bundled style.")
    parser.add_argument("--render-check", action="store_true", help="Render PDF pages to PNG via PyMuPDF.")
    parser.add_argument("--chrome-path", help="Path to Chrome or Edge executable.")
    parser.add_argument("--keep-html", action="store_true", help="Keep the generated HTML next to work files.")
    parser.add_argument(
        "--image-profile",
        choices=sorted(IMAGE_PROFILES),
        default="normal",
        help="Image sizing profile.",
    )
    parser.add_argument("--font-cn", default="宋体", help="Preferred Chinese font family.")
    return parser.parse_args()


def fail(message: str) -> None:
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def ensure_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        fail(f"Required tool not found on PATH: {name}")
    return path


def find_chrome(chrome_path: str | None) -> str:
    if chrome_path:
        candidate = Path(chrome_path).expanduser()
        if candidate.exists():
            return str(candidate)
        fail(f"--chrome-path does not exist: {candidate}")

    for exe in ("chrome", "chrome.exe", "msedge", "msedge.exe", "google-chrome", "chromium", "chromium-browser"):
        found = shutil.which(exe)
        if found:
            return found

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    program_files = [os.environ.get("PROGRAMFILES", ""), os.environ.get("PROGRAMFILES(X86)", "")]
    common_paths = [
        Path(program_files[0]) / "Google/Chrome/Application/chrome.exe",
        Path(program_files[1]) / "Google/Chrome/Application/chrome.exe",
        Path(program_files[0]) / "Microsoft/Edge/Application/msedge.exe",
        Path(program_files[1]) / "Microsoft/Edge/Application/msedge.exe",
        Path(local_app_data) / "Google/Chrome/Application/chrome.exe",
    ]
    for path in common_paths:
        if path.exists():
            return str(path)

    fail("Chrome/Edge executable not found. Pass --chrome-path.")


def is_remote_or_special(target: str) -> bool:
    stripped = target.strip()
    if not stripped or stripped.startswith("#"):
        return True
    parsed = urlparse(stripped)
    return parsed.scheme.lower() in REMOTE_SCHEMES


def strip_url_fragment(target: str) -> tuple[str, str]:
    for marker in ("#", "?"):
        if marker in target:
            base, suffix = target.split(marker, 1)
            return base, marker + suffix
    return target, ""


def to_file_uri(target: str, base_dir: Path) -> str:
    decoded = html.unescape(target.strip())
    if is_remote_or_special(decoded):
        return target

    base_target, suffix = strip_url_fragment(decoded)
    local_path = Path(base_target)
    if not local_path.is_absolute():
        local_path = base_dir / local_path
    local_path = local_path.resolve()
    return local_path.as_uri() + suffix


MD_IMAGE_RE = re.compile(r"!\[([^\]]*)\]\(([^)\n]+)\)")
HTML_IMG_SRC_RE = re.compile(r"(<img\b[^>]*?\bsrc=[\"'])([^\"']+)([\"'][^>]*>)", re.IGNORECASE)


def rewrite_markdown_image_paths(markdown: str, base_dir: Path) -> str:
    def replace_md_image(match: re.Match[str]) -> str:
        alt = match.group(1)
        raw_target = match.group(2).strip()
        title = ""

        if raw_target.startswith("<") and ">" in raw_target:
            destination, rest = raw_target[1:].split(">", 1)
            title = rest.strip()
        else:
            title_match = re.match(r"([^\"'\s]+)(\s+[\"'].*[\"'])$", raw_target)
            if title_match:
                destination = title_match.group(1)
                title = title_match.group(2).strip()
            else:
                destination = raw_target

        rewritten = to_file_uri(destination, base_dir)
        if title:
            rewritten = f"{rewritten} {title}"
        return f"![{alt}]({rewritten})"

    markdown = MD_IMAGE_RE.sub(replace_md_image, markdown)

    def replace_html_img(match: re.Match[str]) -> str:
        return f"{match.group(1)}{to_file_uri(match.group(2), base_dir)}{match.group(3)}"

    return HTML_IMG_SRC_RE.sub(replace_html_img, markdown)


def build_effective_css(base_css: Path, custom_css: Path | None, output_css: Path, font_cn: str, profile: str) -> None:
    if not base_css.exists():
        fail(f"Bundled CSS not found: {base_css}")
    values = IMAGE_PROFILES[profile]
    css = base_css.read_text(encoding="utf-8")
    css = css.replace("__FONT_CN__", font_cn)
    css = css.replace("__RASTER_MAX_WIDTH__", values["raster_width"])
    css = css.replace("__RASTER_MAX_HEIGHT__", values["raster_height"])
    css = css.replace("__SVG_MAX_WIDTH__", values["svg_width"])
    css = css.replace("__SVG_MAX_HEIGHT__", values["svg_height"])
    if custom_css:
        if not custom_css.exists():
            fail(f"Custom CSS not found: {custom_css}")
        css += "\n\n/* Custom override */\n" + custom_css.read_text(encoding="utf-8")
    output_css.write_text(css, encoding="utf-8")


def run(cmd: list[str], cwd: Path | None = None) -> None:
    printable = " ".join(f'"{part}"' if " " in part else part for part in cmd)
    print(f"RUN: {printable}")
    completed = subprocess.run(cmd, cwd=str(cwd) if cwd else None, text=True, capture_output=True)
    if completed.stdout:
        print(completed.stdout)
    if completed.returncode != 0:
        if completed.stderr:
            print(completed.stderr, file=sys.stderr)
        fail(f"Command failed with exit code {completed.returncode}")
    if completed.stderr:
        print(completed.stderr, file=sys.stderr)


def wait_for_stable_file(path: Path, timeout_seconds: float = 20.0) -> bool:
    deadline = time.time() + timeout_seconds
    last_size = -1
    stable_count = 0
    while time.time() < deadline:
        if path.exists():
            size = path.stat().st_size
            if size > 0 and size == last_size:
                stable_count += 1
                if stable_count >= 2:
                    return True
            else:
                stable_count = 0
                last_size = size
        time.sleep(0.5)
    return path.exists() and path.stat().st_size > 0


def render_pdf_checks(pdf_path: Path, check_dir: Path) -> list[Path]:
    try:
        import fitz  # type: ignore
    except ImportError:
        fail("PyMuPDF is required for --render-check. Install with: pip install pymupdf")

    check_dir.mkdir(parents=True, exist_ok=True)
    # Open from bytes and save through an ASCII temp path to avoid Windows
    # Unicode-path edge cases in some PyMuPDF builds.
    doc = fitz.open(stream=pdf_path.read_bytes(), filetype="pdf")
    outputs: list[Path] = []
    zoom = 1.5
    matrix = fitz.Matrix(zoom, zoom)
    with tempfile.TemporaryDirectory(prefix="md2pdf-render-") as temp_render:
        temp_render_dir = Path(temp_render)
        for index in range(doc.page_count):
            page = doc.load_page(index)
            pix = page.get_pixmap(matrix=matrix, alpha=False)
            out = check_dir / f"page-{index + 1:03d}.png"
            temp_out = temp_render_dir / out.name
            pix.save(str(temp_out))
            shutil.move(str(temp_out), str(out))
            outputs.append(out)
    doc.close()
    return outputs


def main() -> None:
    args = parse_args()
    input_path = Path(args.input).expanduser().resolve()
    if not input_path.exists():
        fail(f"Input Markdown not found: {input_path}")
    if input_path.suffix.lower() not in {".md", ".markdown"}:
        fail(f"Input must be a Markdown file: {input_path}")

    output_pdf = Path(args.output).expanduser().resolve() if args.output else input_path.with_suffix(".pdf")
    output_pdf.parent.mkdir(parents=True, exist_ok=True)

    ensure_tool("pandoc")
    chrome = find_chrome(args.chrome_path)

    persistent_workdir = args.keep_html or args.workdir or args.render_check
    temp_context = None
    if args.workdir:
        workdir = Path(args.workdir).expanduser().resolve()
        workdir.mkdir(parents=True, exist_ok=True)
    elif persistent_workdir:
        workdir = output_pdf.parent / f"{output_pdf.stem}_pdf_work"
        workdir.mkdir(parents=True, exist_ok=True)
    else:
        temp_context = tempfile.TemporaryDirectory(prefix="md-to-pdf-cn-")
        workdir = Path(temp_context.name)

    pdf_md = workdir / f"{input_path.stem}.pdf-source.md"
    html_path = workdir / f"{input_path.stem}.html"
    effective_css = workdir / "pdf-cn-style.effective.css"

    source = input_path.read_text(encoding="utf-8-sig")
    rewritten = rewrite_markdown_image_paths(source, input_path.parent)
    pdf_md.write_text(rewritten, encoding="utf-8")
    build_effective_css(DEFAULT_CSS, Path(args.css).expanduser().resolve() if args.css else None, effective_css, args.font_cn, args.image_profile)

    pandoc_cmd = [
        "pandoc",
        "--from",
        "gfm",
        "--to",
        "html5",
        "--standalone",
        str(pdf_md),
        "--css",
        str(effective_css),
        "--metadata",
        f"pagetitle={input_path.stem}",
        "-o",
        str(html_path),
    ]
    run(pandoc_cmd, cwd=input_path.parent)

    chrome_profile = workdir / "chrome-profile"
    if chrome_profile.exists():
        shutil.rmtree(chrome_profile)
    if output_pdf.exists():
        output_pdf.unlink()
    chrome_cmd = [
        chrome,
        "--headless=new",
        "--disable-gpu",
        "--allow-file-access-from-files",
        "--no-pdf-header-footer",
        "--virtual-time-budget=12000",
        "--run-all-compositor-stages-before-draw",
        f"--user-data-dir={chrome_profile}",
        f"--print-to-pdf={output_pdf}",
        html_path.as_uri(),
    ]
    run(chrome_cmd)
    if not wait_for_stable_file(output_pdf):
        fail(f"Chrome did not create PDF: {output_pdf}")
    if chrome_profile.exists():
        shutil.rmtree(chrome_profile)

    check_outputs: list[Path] = []
    if args.render_check:
        check_outputs = render_pdf_checks(output_pdf, workdir / "render-check")

    if not args.keep_html and not args.workdir and not args.render_check and temp_context:
        temp_context.cleanup()

    print("")
    print(f"PDF: {output_pdf}")
    if args.keep_html or args.workdir or args.render_check:
        print(f"HTML: {html_path}")
        print(f"PDF source Markdown: {pdf_md}")
    if check_outputs:
        print(f"Render check directory: {check_outputs[0].parent}")
        for path in check_outputs:
            print(f"  {path}")


if __name__ == "__main__":
    main()
