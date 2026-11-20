#!/usr/bin/env python3
import json
import os
import re
import time
import subprocess
from pathlib import Path
from typing import Iterable

CONFIG_PATH = Path.home() / ".config" / "cue-tui" / "config.json"

import chardet
from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    DirectoryTree,
    Footer,
    Header,
    Input,
    Label,
    ProgressBar,
    RichLog,
    Static,
)


def get_utf8_cue_content(cue_path: str) -> str:
    """Detects the encoding of a CUE file and returns its content in UTF-8."""
    with open(cue_path, "rb") as f:
        raw_data = f.read()

    detected = chardet.detect(raw_data)
    encoding = detected["encoding"] if detected["encoding"] else "cp1251"

    try:
        return raw_data.decode(encoding, errors="ignore")
    except Exception:
        return raw_data.decode("cp1251", errors="ignore")


def cue_time_to_ffmpeg(cue_ts: str) -> str:
    """Converts CUE timestamp (MM:SS:FF at 75fps) to FFmpeg HH:MM:SS.mmm format."""
    parts = cue_ts.strip().split(":")
    if len(parts) != 3:
        return "00:00:00.000"
    total_mins, secs, frames = int(parts[0]), int(parts[1]), int(parts[2])
    hours, mins = divmod(total_mins, 60)
    millis = round((frames / 75.0) * 1000)
    return f"{hours:02d}:{mins:02d}:{secs:02d}.{millis:03d}"



def parse_cue_data(cue_content: str) -> tuple[str | None, list[dict]]:
    """Parses a CUE sheet and returns (referenced_file, list_of_track_dicts)."""
    referenced_file = None
    tracks = []
    current_track = None

    for raw_line in cue_content.splitlines():
        line = raw_line.strip()

        if line.upper().startswith("FILE "):
            match = re.search(r'FILE\s+"([^"]+)"', line, re.IGNORECASE)
            if match and not referenced_file:
                referenced_file = match.group(1)

        elif line.upper().startswith("TRACK "):
            if current_track:
                tracks.append(current_track)
            parts = line.split()
            track_num = int(parts[1]) if len(parts) >= 2 and parts[1].isdigit() else len(tracks) + 1
            current_track = {
                "num": track_num,
                "title": f"Track {track_num}",
                "start_cue": "00:00:00",
                "start_ffmpeg": "00:00.000",
            }

        elif line.upper().startswith("TITLE ") and current_track is not None:
            title_val = line[6:].strip().strip('"')
            if title_val:
                current_track["title"] = title_val

        elif line.upper().startswith("INDEX 01 ") and current_track is not None:
            parts = line.split()
            if len(parts) >= 3:
                current_track["start_cue"] = parts[2]
                current_track["start_ffmpeg"] = cue_time_to_ffmpeg(parts[2])

    if current_track:
        tracks.append(current_track)

    return referenced_file, tracks


class ConfirmDeleteModal(ModalScreen[bool]):
    """Popup modal asking for confirmation before deleting source files."""

    CSS = """
    ConfirmDeleteModal { align: center middle; }
    #dialog {
        padding: 1 2; width: 60; height: auto;
        border: thick $error; background: $surface;
    }
    #modal_buttons { margin-top: 1; align: right middle; height: auto; }
    Button { margin-left: 1; }
    """

    def __init__(self, files_to_delete: list[str]) -> None:
        super().__init__()
        self.files_to_delete = files_to_delete

    def compose(self) -> ComposeResult:
        count = len(self.files_to_delete)
        preview = "\n".join(f"• {os.path.basename(f)}" for f in self.files_to_delete[:5])
        if count > 5:
            preview += f"\n...and {count - 5} more."

        with Vertical(id="dialog"):
            yield Label(f"[bold red]⚠️ Delete {count} Original Audio File(s)?[/]")
            yield Static(f"\nThis action cannot be undone:\n{preview}")
            with Horizontal(id="modal_buttons"):
                yield Button("Keep Files", variant="default", id="cancel_btn")
                yield Button("Delete Permanently", variant="error", id="confirm_btn")

    @on(Button.Pressed, "#confirm_btn")
    def confirm(self) -> None:
        self.dismiss(True)

    @on(Button.Pressed, "#cancel_btn")
    def cancel(self) -> None:
        self.dismiss(False)
class FilteredDirectoryTree(DirectoryTree):
    """Shows non-hidden folders, .cue sheets, and supported audio files."""

    ALLOWED_EXTS = {".cue", ".flac", ".wav", ".ape"}

    def filter_paths(self, paths: Iterable[Path]) -> Iterable[Path]:
        return [
            p
            for p in paths
            if not p.name.startswith(".")
            and (p.is_dir() or p.suffix.lower() in self.ALLOWED_EXTS)
        ]



class CueSplitterTUI(App):
    TITLE = "CUE Audio Splitter"
    BINDINGS = [
        Binding("ctrl+r", "start_split", "Start Split", show=True),
        Binding("ctrl+l", "clear_log", "Clear Log", show=True),
        Binding("ctrl+q", "quit", "Quit", show=True),
        Binding("escape", "hide_help_panel", "Close Keys", show=False),
    ]

    CSS = """
    Screen { layout: horizontal; }
    #sidebar { width: 35%; border-right: tall $primary; padding: 1; }
    #main { width: 65%; padding: 1; }
    .box { margin-bottom: 1; }
    #controls { height: auto; margin-bottom: 1; }
    Button { margin-right: 1; }
    DataTable { height: 10; border: solid $secondary; margin-bottom: 1; }
    RichLog { border: solid $accent; height: 1fr; background: $surface; }
    """

    def compose(self) -> ComposeResult:
        music_dir = os.path.expanduser("~/Music")
        start_dir = music_dir if os.path.isdir(music_dir) else os.path.expanduser("~")

        yield Header()
        with Vertical(id="sidebar"):
            yield Static("📁 [bold]Browse Folder or Click a .cue File:[/]", classes="box")
            yield FilteredDirectoryTree(start_dir, id="dir_tree")

        with Vertical(id="main"):
            yield Static("🎯 [bold]Target Directory Path:[/]")
            yield Input(value=start_dir, id="path_input", classes="box")

            yield Checkbox(
                "Prompt to delete original files (.flac/.wav/.ape) when finished",
                id="delete_originals",
                classes="box",
            )

            with Horizontal(id="controls"):
                yield Button("▶ Start Splitting (Ctrl+R)", variant="success", id="start_btn")
                yield Button("Clear Log (Ctrl+L)", variant="default", id="clear_btn")

            yield Static("🎵 [bold]Track Preview (Select a .cue file on the left):[/]")
            yield DataTable(id="preview_table")

            yield ProgressBar(total=100, show_eta=False, id="progress", classes="box")
            yield RichLog(id="log", highlight=True, markup=True)
        yield Footer()

    def on_mount(self) -> None:
        self._theme_loaded = False
        table = self.query_one("#preview_table", DataTable)
        table.add_columns("#", "Track Title", "Start Time")
        self.call_after_refresh(self._load_saved_theme)

    def _load_saved_theme(self) -> None:
        cfg_file = os.path.join(os.path.expanduser("~"), ".config", "cue-tui", "config.json")
        if os.path.isfile(cfg_file):
            try:
                with open(cfg_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                saved_theme = data.get("theme")
                if saved_theme and saved_theme in self.available_themes:
                    self.theme = saved_theme
            except Exception as e:
                self.write_log(f"[yellow]Theme load warning: {e}[/]")
        self._theme_loaded = True

    def watch_theme(self, theme: str) -> None:
        """Automatically saves the theme whenever the user changes it via Ctrl+P."""
        if not getattr(self, "_theme_loaded", False):
            return
        cfg_dir = os.path.join(os.path.expanduser("~"), ".config", "cue-tui")
        cfg_file = os.path.join(cfg_dir, "config.json")
        try:
            os.makedirs(cfg_dir, exist_ok=True)
            with open(cfg_file, "w", encoding="utf-8") as f:
                json.dump({"theme": theme}, f, indent=2)
        except Exception as e:
            self.write_log(f"[yellow]Theme save warning: {e}[/]")







    @on(DirectoryTree.DirectorySelected)
    def on_dir_selected(self, event: DirectoryTree.DirectorySelected) -> None:
        self.query_one("#path_input", Input).value = str(event.path)

    @on(DirectoryTree.FileSelected)
    def on_file_selected(self, event: DirectoryTree.FileSelected) -> None:
        file_path = str(event.path)
        self.query_one("#path_input", Input).value = os.path.dirname(file_path)

        if file_path.lower().endswith(".cue"):
            self.populate_preview_table(file_path)
        else:
            self.query_one("#preview_table", DataTable).clear()


    def populate_preview_table(self, cue_path: str) -> None:
        table = self.query_one("#preview_table", DataTable)
        table.clear()

        try:
            content = get_utf8_cue_content(cue_path)
            _, tracks = parse_cue_data(content)
            for tr in tracks:
                table.add_row(f"{tr['num']:02d}", tr["title"], tr["start_cue"])
        except Exception as e:
            self.write_log(f"[red]Could not preview {os.path.basename(cue_path)}: {e}[/]")

    def action_clear_log(self) -> None:
        self.query_one("#log", RichLog).clear()

    def action_start_split(self) -> None:
        start_btn = self.query_one("#start_btn", Button)
        if not start_btn.disabled:
            self.on_start()

    @on(Button.Pressed, "#clear_btn")
    def on_clear_btn(self) -> None:
        self.action_clear_log()

    @on(Button.Pressed, "#start_btn")
    def on_start(self) -> None:
        target_dir = self.query_one("#path_input", Input).value.strip()
        ask_delete = self.query_one("#delete_originals", Checkbox).value

        if not os.path.isdir(target_dir):
            self.write_log("[bold red]❌ Error: Selected path is not a valid directory.[/]")
            return

        self.query_one("#start_btn", Button).disabled = True
        self.query_one("#log", RichLog).clear()
        self.run_batch_split(target_dir, ask_delete)

    def write_log(self, message: str) -> None:
        self.query_one("#log", RichLog).write(message)

    def update_progress(self, total: int, progress: int) -> None:
        bar = self.query_one("#progress", ProgressBar)
        bar.update(total=total, progress=progress)
    @work(thread=True)
    def run_batch_split(self, target_dir: str, ask_delete: bool) -> None:
        start_time = time.time()
        cue_files = []

        self.call_from_thread(self.write_log, f"🔍 Scanning [cyan]{target_dir}[/]...")
        for root, _, files in os.walk(target_dir):
            for file in files:
                if file.lower().endswith(".cue") and not file.endswith("_utf8_temp.cue"):
                    cue_files.append(os.path.join(root, file))

        if not cue_files:
            self.call_from_thread(self.write_log, "[yellow]⚠️ No .cue files found in directory.[/]")
            self.call_from_thread(self.finish_run, [], False)
            return

        self.call_from_thread(self.update_progress, len(cue_files), 0)
        files_created = 0
        errors = []
        processed_audio_files = []

        for idx, cue_path in enumerate(cue_files, start=1):
            cue_name = os.path.basename(cue_path)
            self.call_from_thread(self.write_log, f"\n🎬 Processing [bold]{cue_name}[/]...")

            success, result, track_count = self.split_single_cue(cue_path)
            if success:
                if result not in processed_audio_files:
                    processed_audio_files.append(result)
                files_created += track_count
                self.call_from_thread(
                    self.write_log, f"   [green]✔ Split into {track_count} tracks[/]"
                )
            else:
                errors.append(f"{cue_name}: {result}")
                self.call_from_thread(self.write_log, f"   [red]❌ {result}[/]")

            self.call_from_thread(self.update_progress, len(cue_files), idx)

        duration = round(time.time() - start_time, 2)
        summary = (
            "\n[bold cyan]================ EXECUTION REPORT ================[/]\n"
            f"⏱  Elapsed time: [bold]{duration}s[/]\n"
            f"🎵 Tracks created: [bold green]{files_created}[/]\n"
            f"❌ Errors: [bold red]{len(errors)}[/]\n"
            "[bold cyan]==================================================[/]"
        )
        self.call_from_thread(self.write_log, summary)
        self.call_from_thread(self.finish_run, processed_audio_files, ask_delete)

    def find_audio_file(self, folder: str, base_name: str, referenced_file: str | None) -> tuple[str | None, str | None]:
        """Finds the matching audio file using the CUE's FILE directive first, then base_name."""
        valid_exts = {".flac", ".wav", ".ape", ".wv"}

        if referenced_file:
            ref_path = os.path.join(folder, os.path.basename(referenced_file))
            if os.path.isfile(ref_path):
                return ref_path, os.path.splitext(ref_path)[1]
            ref_stem = os.path.splitext(os.path.basename(referenced_file))[0]
            for entry in os.listdir(folder):
                stem, ext = os.path.splitext(entry)
                if stem == ref_stem and ext.lower() in valid_exts:
                    return os.path.join(folder, entry), ext

        for entry in os.listdir(folder):
            stem, ext = os.path.splitext(entry)
            if stem == base_name and ext.lower() in valid_exts:
                return os.path.join(folder, entry), ext

        return None, None

    def split_single_cue(self, cue_path: str) -> tuple[bool, str, int]:
        folder = os.path.dirname(cue_path)
        base_name = os.path.splitext(os.path.basename(cue_path))[0]

        cue_content = get_utf8_cue_content(cue_path)
        referenced_file, tracks = parse_cue_data(cue_content)

        if not tracks:
            return False, "No valid tracks found in CUE sheet", 0

        audio_file, audio_ext = self.find_audio_file(folder, base_name, referenced_file)
        if not audio_file:
            return False, "Matching audio file (.flac/.wav/.ape/.wv) not found", 0

        for i, tr in enumerate(tracks):
            track_num = tr["num"]
            title = tr["title"]
            start_time = tr["start_ffmpeg"]

            safe_title = "".join(
                c for c in title if c.isalpha() or c.isdigit() or c in " ' -_()"
            ).strip()
            if not safe_title:
                safe_title = f"Track {track_num}"

            output_file = os.path.join(folder, f"{track_num:02d} - {safe_title}{audio_ext}")

            if os.path.abspath(output_file) == os.path.abspath(audio_file):
                output_file = os.path.join(folder, f"{track_num:02d} - {safe_title} (split){audio_ext}")

            cmd = ["ffmpeg", "-loglevel", "error", "-y", "-i", audio_file, "-ss", start_time]
            if i + 1 < len(tracks):
                cmd.extend(["-to", tracks[i + 1]["start_ffmpeg"]])

            cmd.extend([
                "-c", "copy",
                "-metadata", f"title={title}",
                "-metadata", f"track={track_num}",
                output_file,
            ])

            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            if proc.returncode != 0:
                err_msg = proc.stderr.strip() or f"FFmpeg failed on track {track_num}"
                return False, err_msg, 0

        return True, audio_file, len(tracks)

    def finish_run(self, processed_audio_files: list[str], ask_delete: bool) -> None:
        self.query_one("#start_btn", Button).disabled = False

        if ask_delete and processed_audio_files:
            def handle_delete_decision(confirmed: bool) -> None:
                if confirmed:
                    self.write_log("\n🗑 [yellow]Deleting original source files...[/]")
                    for src_file in processed_audio_files:
                        try:
                            os.remove(src_file)
                            self.write_log(f"   ✔ Deleted: {os.path.basename(src_file)}")
                        except Exception as e:
                            self.write_log(
                                f"   [red]❌ Failed to delete {os.path.basename(src_file)}: {e}[/]"
                            )
                else:
                    self.write_log("\n🛡 [green]Original monolithic source files preserved.[/]")

            self.push_screen(ConfirmDeleteModal(processed_audio_files), handle_delete_decision)


if __name__ == "__main__":
    CueSplitterTUI().run()
