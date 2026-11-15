# MKV Episode Manager — Windows 11

A Python/PySide6 desktop app to help inspect, identify and safely name MakeMKV movie and TV files for Jellyfin. **Original MKV files are never changed**, and exported copies require explicit review/approval and SHA-256 verification.

> **Release status:** **v0.4.2** — the approved stable release, combining poster-first TMDB selection, subtitle OCR caching, SubDL reference downloading and dialogue comparison. The application is **not** yet a fully automatic movie or episode recognizer. Always review its proposed filename.

## Third-party applications and dependencies

The following table lists the tools actually used by the application or its optional subtitle identification features. Download only from the linked official projects.

| Application / service | Required? | What we use it for | Official download / documentation |
|---|---|---|---|
| **Windows 11** | Target operating system | Runs the desktop application | [Microsoft](https://www.microsoft.com/windows/windows-11) |
| **Python 3.11 (64-bit)** | **Required** for this source build | Runs MKV Episode Manager and its Python modules | [Python 3.11 releases](https://www.python.org/downloads/) |
| **PySide6 (Qt for Python)** | **Required** Python package | Desktop interface. Installed automatically from `requirements.txt` by `START_WINDOWS.bat` | [Qt for Python](https://doc.qt.io/qtforpython-6/) |
| **FFmpeg + FFprobe** | **Required for video inspection, scene galleries and subtitle extraction** | Reads MKV technical details, samples frames, converts embedded text subtitles | [FFmpeg](https://ffmpeg.org/download.html) |
| **SeConv (Subtitle Edit Batch Converter)** | **Required for OCR of DVD/Blu-ray image subtitles**; otherwise optional | Converts DVD VobSub / Blu-ray PGS image subtitle tracks into text using OCR | [Subtitle Edit releases — SeConv-Windows-x64.zip](https://github.com/SubtitleEdit/subtitleedit/releases) |
| **Tesseract OCR + English language data** | **Required with SeConv for image-subtitle OCR**; otherwise optional | Recognises text from subtitle images | [Tesseract Windows installers (UB Mannheim)](https://github.com/UB-Mannheim/tesseract/wiki) |
| **TMDB account + API Read Access Token (or v3 key)** | Optional; needed for TMDB lookup | Movie/TV metadata, posters, title/year selection, episode catalogues | [TMDB API settings](https://www.themoviedb.org/settings/api) |
| **SubDL account + API key** | Optional; needed for **automatic online subtitle references** | Searches for reference subtitles by *user-provided* movie/series title, TMDB ID and TV season | [SubDL API docs](https://subdl.com/api-doc) |
| **MakeMKV** | Separate ripping tool, not needed to run this app | Produces the original MKV rips that this app imports | [MakeMKV](https://www.makemkv.com/) |
| **Jellyfin** | Optional | Media server for renamed exported files; not part of the renaming process | [Jellyfin](https://jellyfin.org/) |

**You do not need to install Subtitle Edit's graphical editor separately** just to run OCR if you already have SeConv and Tesseract. SeConv is a separate release asset; it is not necessarily included in a Subtitle Edit GUI ZIP.

## Windows 11 setup — step by step

1. Install **Python 3.11 64-bit**.
2. Download or clone **main** into a **new** folder (keep your previous v0.4 installation as a backup).
3. Install **FFmpeg** and make sure both `ffmpeg` and `ffprobe` are on Windows **PATH**.
4. For **DVD image-subtitle OCR**, download **SeConv-Windows-x64.zip** from the official Subtitle Edit releases, extract it, and add the **folder containing `seconv.exe`** to your Windows **User Path**. Install Tesseract with English language data and add the folder containing `tesseract.exe` to User Path.
5. Open a **new** PowerShell window and verify:
   ```powershell
   py -3.11 --version
   ffmpeg -version
   ffprobe -version
   seconv --version
   seconv list-ocr-engines
   tesseract --version
   tesseract --list-langs
   ```
   For image subtitles, `seconv list-ocr-engines` should show **tesseract: installed**, and `tesseract --list-langs` should include **eng**. The SeConv/Tesseract checks are optional when you only handle text subtitles or inspect metadata.
6. Double-click **`START_WINDOWS.bat`**. It creates a virtual environment and installs **PySide6** automatically. Internet access is needed for first-run package installation.
7. For online services, enter your **TMDB token** and/or your **separate SubDL API key** in the corresponding masked fields. Never share credentials in screenshots, issues, repository commits or support logs.

**Example installation paths only:** One working Windows setup uses `A:\Subtitle Edit\seconv` and `A:\Subtitle Edit\tesseract`. Your own folders can be different. Add directories to PATH, **not** the individual `.exe` paths. Restart PowerShell and the app after editing PATH.

## What works in v0.4.2

- Import MakeMKV files with generic names such as `C1_t00.mkv` or `title_t00.mkv`. **The app never guesses the movie/series title from an imported MKV filename.** The title field stays blank unless you already entered a title yourself. Choose **Movie** or a TV season mode, enter the title printed on the disc cover (for TV, select the season), and use TMDB to confirm the correct title. Imported filenames remain unchanged.
- **TMDB poster-first search**: pressing **Find movie / series** shows each candidate with its poster thumbnail, title, release year and short synopsis. Click the poster/title row once to select the right film or TV series. Poster images load progressively so the window stays responsive. If a poster is missing, its title remains selectable. **TMDB results are suggestions, not verified content matches**.
- **Readable subtitle results**: the analysis summary shows the best evidence, OCR dialogue cue count and downloaded reference count. **Diagnostics** beside **OK** opens the original complete technical report (streams, OCR, download outcomes, and matching scores). This is informational only and never approves output filenames.
- **Video inspection and six-frame gallery**: FFmpeg/FFprobe examine source files read-only. Automatic scene-to-reference recognition is **not yet implemented**.
- **Analyse subtitles**: FFprobe inventories tracks; FFmpeg extracts supported embedded text subtitles; **SeConv + Tesseract** can attempt OCR on English image-based DVD subtitles (experimental). The first OCR run can take more than ten minutes.
- **Online subtitle references**: if a SubDL key is entered, the app tries the selected TMDB ID first and falls back to the DVD-cover title when needed; available reference subtitles are downloaded temporarily and compared against extracted English dialogue. Distinct statuses describe failed searches, missing listings, failed downloads, and insufficient matches. You **do not need a pre-existing local subtitle collection**.
- **Match evidence**: reports overlap and matching-cue counts. Scores are heuristic, **not a probability or verified identification percentage**. Online lookup, OCR, reference coverage and editions can fail, and successful OCR alone does not prove the title.
- **Review and export**: every file must be approved before a verified copy is exported into a separate destination. Never overwrite original source files.

## v0.4.3 development — SubDL reference download cache

On the **v0.4.3 development branch**, MKV Episode Manager locally caches successfully downloaded SubDL subtitle references so analysing more MKVs from the same season can reuse existing reference files without making another charged subtitle download. This addresses SubDL's **50-downloads-per-day free account allowance**; search API requests still occur when analysing an MKV. Cache hits and new download attempts are shown in Subtitle Analysis and Diagnostics.

- Cache location on Windows: `%LOCALAPPDATA%\\MKVEpisodeManager\\reference_cache`.
- Cache lifetime: up to **30 days**; maximum total disk usage **512 MB**. Expired files are removed automatically as new entries are stored.
- Entries are scoped to the user's SubDL API key using opaque hashes. Neither the key nor signed download URLs are saved to cache filenames or content.
- When SubDL replies **HTTP 429**, the app stops making additional downloads for that analysis, instead of repeating the blocked requests. The result explains when identification could not proceed because references were unavailable.
- The cache can be cleared by deleting the **reference_cache** folder with the application closed; this does not affect the separate OCR transcript cache or any original MKV.
- References must already have been acquired after installing this update; it cannot recover earlier references that v0.4.2 only held temporarily. It does not increase the provider's daily allowance or guarantee full-season coverage.
- This is a **development feature**, separate from approved stable v0.4.2; a Windows confirmation is still required.

## Known limitations / next development improvements

- **Validation scope:** *Flight (2012)* was tested successfully on Windows 11 (17 reference subtitle files downloaded, 1,974 cached English cues, supported heuristic dialogue match). Other movies, discs, subtitle formats and complete TV seasons need additional real-world testing.
- DVD `dvd_subtitle` / Blu-ray PGS streams are bitmap images: extraction requires both **SeConv and Tesseract**. OCR must be checked for accuracy; some streams or language selections may fail.
- SubDL API searches require a known title, TMDB identity or season; the service does **not** supply a general reverse-dialogue search across every film/episode. Some searches return no references.
- OCR comparison against online references is experimental, with no calibrated accuracy %. A no-match result must remain **unverified**, not a guessed title.
- **Whole-season automatic episode assignment, audio transcription and automatic visual reference matching are not implemented yet.** Do not assign episode numbers by MKV file order.
- **Persistent English OCR caching is implemented and was tested on Windows 11**: cached subtitle text is stored locally in `%LOCALAPPDATA%\\MKVEpisodeManager\\subtitle_cache`, keyed to source file metadata plus sampled bytes. Repeated analysis can reuse it without rerunning OCR; use **Clear OCR cache** to remove derived transcripts. The user can import a previously extracted SRT via **Import OCR SRT**.
- Video inspection, diagnostics and safe-copy export rely on FFmpeg/Python dependencies, but the originals remain untouched.

See [v0.4.2 subtitle notes](docs/V0.4.2_SUBTITLE_IDENTIFICATION.md) for technical details and testing instructions.

## Running tests

From the checked-out source folder:

```powershell
py -3.11 -m unittest discover -s tests -v
```

These are mostly offline/synthetic tests. They do not substitute for testing actual DVD/Blu-ray OCR and provider access on Windows.

## GitHub release policy

Development changes stay on feature branches/draft pull requests. A **stable release merge to `main` requires the project owner's explicit approval**. The owner approved promoting the successfully tested v0.4.2 features on 16 November 2026.
