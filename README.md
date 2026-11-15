# MKV Episode Manager v0.4.1 — Iteration 1 (Windows 11 test build)

This is a **working Python/PySide6 desktop application**, not a mockup. It adds TMDB online title search, movie year/title autofill, poster retrieval, TV season episode catalogues, and six-frame scene galleries to the original manual-review/verified-copy workflow.

## Install

1. Install **Python 3.11 64-bit**. Keep the Python version you already installed if it is 3.11.
2. Extract this ZIP to its own folder, not on top of the old v0.4 installation.
3. Double-click **START_WINDOWS.bat**. Internet is required to install PySide6 on first launch.
4. Install **FFmpeg** (both `ffmpeg.exe` and `ffprobe.exe` on Windows PATH) for scene galleries and technical inspection.
5. To use TMDB searches, create your own free TMDB account and obtain an **API Read Access Token** or v3 API key from https://www.themoviedb.org/settings/api . Paste it into the **TMDB token** field in the app. The token is held in memory during the session only; it is not written to project files or reports. Treat it as a secret.

## Movie workflow

1. Select **Movie**, then **Import MKVs**.
2. Click **Find movie / series**. The search uses the current title as a starting point, but you can change it.
3. Select the correct movie **and year** from the results. The app fills movie title, year and proposed filename automatically.
4. Select a file row and click **Scene gallery** to extract six evenly spaced video frames. These are for visual confirmation only.
5. Review the proposed name. Tick **Approve** only if correct. Export to a new empty folder **outside the source tree**. The app copies without modifying source files, verifies SHA-256, then atomically finalizes without overwriting.

## TV workflow

1. Select **Complete TV Season** or **Incomplete TV Season**; import MKVs.
2. Search for and select the correct series.
3. Set season number, click **Fetch season episodes** to retrieve episode numbers/titles.
4. **Manually identify which episode is in each MKV** (using your own viewing or other evidence). Enter its episode number; if in the retrieved catalogue, its title fills automatically. Do not assign episode numbers by MakeMKV title order alone.
5. Use scene galleries to help inspect files. Approve each row and export only after verifying.

## Honest scope / limitations

- TMDB movie/series identification uses **title search**, not actual video-content recognition. A movie match must be confirmed by the user.
- **No automatic visual scene-to-reference matching** is implemented. Scene galleries are local evidence for human review; posters are metadata images, not reference frames for individual episodes.
- **No audio or dialogue identification** is implemented yet.
- TV catalogue lookup **does not identify the actual episode in an MKV**; it fills the title after you supply an episode number.
- TMDB needs internet access and user-provided credentials. Not every title has complete metadata.
- No direct Unraid export. Originals remain untouched. Use a small test set first.
- An interrupted export can leave a `.part` file. Do not delete it until sure no copy is active.
- The program does not alter source MKVs. It can write temporary thumbnails and separate project/report/output files.

## Tests

Run `py -3.11 -m unittest discover -s tests -v` from this folder. Tests cover naming, TMDB filename parsing, verified copying, collision rejection, source protection, and project round-trip. They do not substitute for testing with actual DVDs on Windows.
