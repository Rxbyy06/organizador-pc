# OrganizadorPC

A Windows tray app, written in Python, that keeps my files in order without getting in the way. It lives as an icon next to the clock and starts with Windows. I use it every day.

> The user interface and the code comments are in Spanish. The user guide is [LEEME.md](LEEME.md) and the technical overview is [docs/TRASPASO.md](docs/TRASPASO.md).

## How it was built

This is an **AI-assisted project**. I came up with the idea, defined what the app had to do and made the design decisions. Examples: OneDrive as the hub of the sync, never deleting anything permanently, a brake that asks before mass deletions, a weekly review instead of constant pop-ups. I also tested it on my own files and reported what went wrong.

**All of the code was written by [Claude Code](https://claude.com/claude-code)**, Anthropic's AI coding agent, working from those requirements. I'm sharing it as an example of building a real everyday tool by directing an AI agent, not as a sample of code I wrote by hand.

## Features

- **Downloads organizer.** When a download finishes, a small window suggests a folder and a file name. The suggestion comes from learned rules (course, website of origin), from TF-IDF similarity between the file's text and each folder, and from keywords. Nothing moves without a click, and it warns about duplicates, new versions and statement/solution pairs.
- **Weekly cleanup and review.** Anything that has been in Downloads for 7 days goes to the Recycle Bin, with a warning the day before. Every Monday a window shows a summary of the week and lets me review old screenshots.
- **Three-way sync.** Keeps OneDrive and two Google Drive accounts identical, with OneDrive in the middle. It detects moves and renames, keeps both versions on conflicts, and stops for confirmation before a mass deletion.
- **Word copies of Google Docs.** A Google Apps Script exports each Doc to `.docx`, and the PC places the copy next to the original as read-only.
- **Safe by design.** Nothing is deleted permanently: everything goes to the Recycle Bin, and every action can be undone from the History. Heavy work runs only when the PC is idle, at low CPU and disk priority, and pauses during full-screen apps or on low battery.

## Tech

Python 3.14 · CustomTkinter · pystray · watchdog · PyMuPDF · SQLite · pywin32 · Google Apps Script

## Run it

```bash
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
copy config.example.toml config.toml          # then set your own paths and folders
copy aprendido.example.txt aprendido.txt
.venv\Scripts\python.exe instalar.py          # adds it to Windows startup and the Start menu
```

Set `simulacion = true` in `config.toml` to make the app only log what it would do.

## Tests

```bash
.venv\Scripts\python.exe -m unittest discover tests
```

102 unit tests cover the organizer rules, the cleanup and review (with a simulated clock), the sync engine (with local folders standing in for OneDrive and both Drives), the Word copies and the reports.

## License

[MIT](LICENSE)
