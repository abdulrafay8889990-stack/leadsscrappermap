# Lead Scraper

Windows desktop app that collects business leads from **Google Maps**: name, phone, email, website, address, city, country, rating, reviews and category. It is built for finding businesses that **don't have a website yet**.

## Install

Works on any 64-bit Windows 10/11 PC. Python is not needed. On the first scrape the app downloads the Chromium browser (~150 MB) by itself.

**Option A: setup file (recommended).** Run **`dist\Lead Scraper Setup.exe`**, a single 52 MB file to download or share.

- It installs per user, so no admin rights are needed, to `%LOCALAPPDATA%\Programs\Lead Scraper`.
- It creates Desktop and Start Menu shortcuts and an entry in **Settings > Apps** with **Uninstall**.
- Uninstall removes the app, its shortcuts and its Apps entry, but keeps your leads, CSV/Excel files and lead history.
- Running a newer Setup over an installed copy updates it.

The setup file is not code-signed. Windows **SmartScreen** may warn on a downloaded copy ("More info" → "Run anyway"). On a PC with **Smart App Control** turned on, the first launch can be blocked while Windows checks the new file; starting it again a few seconds later worked in testing. Option B avoids both.

**Option B: zip.** Unzip `dist\Lead Scraper.zip` anywhere and double-click **`Lead Scraper.exe`**. This exe is signed (see below), so Smart App Control never blocks it, but there are no shortcuts and no uninstaller.

**Option C: build and install from this folder** (needs Python 3.10+, plus [Inno Setup 6](https://jrsoftware.org/isinfo.php) for the setup file: `winget install JRSoftware.InnoSetup`):

```powershell
powershell -ExecutionPolicy Bypass -File tools\build.ps1
```

The script:

- builds the app folder;
- installs it to `%LOCALAPPDATA%\Programs\Lead Scraper`;
- creates **Desktop** and **Start Menu** shortcuts;
- writes a fresh `dist\Lead Scraper.zip` and `dist\Lead Scraper Setup.exe`.

Re-run it after changing the code.

### How the .exe works

`Lead Scraper.exe` is Python's own `pythonw.exe` under a new name, so it keeps the **Python Software Foundation signature**. The folder also holds its own Python runtime, only the packages the app needs, and the app code in `app\`.

When the exe starts, `app\sitecustomize.py` (`tools\launcher.py`) runs `main.py`, so double-clicking opens the app. `python313._pth` keeps it isolated from any other Python on the PC.

It is built this way because Windows 11 **Smart App Control** blocks every unsigned `.exe`, including PyInstaller builds, but allows a signed one like this. Because the exe file keeps the Python logo in Explorer, the shortcuts and the app window use the Lead Scraper icon.

To run from source instead: `pip install -r requirements.txt`, then `python -m playwright install chromium`, then `python main.py`.

## Using it

The app uses a light pastel theme: white rounded cards, lavender accents and a gradient header.

**Left sidebar:**

1. **Search**: keywords (one per line) and locations (one per line). The **Cities** button adds cities from 30 countries (USA, UK, Canada, UAE, Saudi Arabia, Pakistan, India, Australia, …). Big cities can be split into areas.
2. **Leads & files**:
   - *How many leads*: total for the run (default and maximum 50,000);
   - *New file every*: a new file after this many leads (default 10,000; 0 = no split files);
   - *File type*: **CSV** (default) or Excel. The line below shows the result, e.g. "50,000 leads → 5 CSV files of 10,000".
3. **Filters**:
   - *No real website (social pages OK)*, *No website at all* or *All businesses*;
   - *Only leads with a phone number*;
   - *Skip leads from earlier runs*: never returns the same business twice; **Reset** forgets the history.
4. **Emails**:
   - *Find emails*: from the business's own website, or for businesses without a website, from online business directories via web search;
   - *Only leads with an email*.
5. **Advanced**:
   - *Split leads evenly across locations*;
   - *Keep going when results run out*: Google Maps lists ~120 places per search, so a country is searched city by city, and a city area by area on a map grid, until *How many leads* is reached;
   - *Run headless*: hide the browser. Keep it visible to solve CAPTCHAs.
   - **Speed**: how many places are opened at once. *Safe* = 1, *Fast* = 3 (default), *Max* = 4.
6. **Start Scraping**. The button turns red to stop. Closing the browser window also stops the run cleanly.

**Main area:**

- **Stat cards**: Leads, With email, No website, Social only, Skipped, Run time with leads/min. Plus live progress and status.
- **Search box** and quick filters **All / With email / No website / Social only**.
- **Copy emails** copies the emails of the current view, one per line.
- **Export** saves all leads or only the current view as `.csv` or `.xlsx` (the chosen file type is the default).
- **Table**:
  - double-click a row to open the place on Google Maps;
  - right-click to copy phone, email or name, or to open the website.
  - It draws up to 5,000 rows at once; exports always contain everything.
- **Live log** at the bottom, with Hide and Clear.

## Where files are

| What | Where |
|---|---|
| Files saved during a run | `Documents\Lead Scraper\exports\<keyword>_<date>\leads_001_1-10000.csv`, `leads_002_10001-20000.csv`, … |
| Autosave of all leads (every 100 leads, every 500 after 5,000, and at the end) | `Documents\Lead Scraper\autosave\` |
| Lead history (no repeats), browser profile (solved CAPTCHAs), log | `%LOCALAPPDATA%\Lead Scraper\` |

The folder buttons in the app open these locations.

## How it works

- **Lead filters.** Websites are classified as *No website*, *Social only* (Facebook, Instagram, WhatsApp, Linktree, …) or *Has website*. Places whose result card already shows a real website are skipped without being opened.
- **Emails.**
  - Website: the homepage plus up to 3 contact/about pages. It reads `mailto:` links, encoded and Cloudflare-protected addresses, and prefers addresses on the business's own domain.
  - No website: one Bing search for `"Business Name" City email`. An address is accepted only from a result that names the business, near the name, or when the address contains the name. A directory's own addresses and placeholders (`jane.doe@`, `noreply@`) are rejected.
- **Keep going.** City centres come from OpenStreetMap (Nominatim). The keyword is then searched on a spiral of zoom-14 map views around the centre (81+ "map areas"). Places already checked are skipped instantly.
- **Speed.**
  - The results list is scrolled while places are already being opened.
  - Several tabs open places at the same time.
  - Each place is read in one call.
  - The website/email lookup runs in the background while the tab moves on.
  - Photos, map tiles and web fonts are blocked, so the visible browser looks bare. CAPTCHA images still load.

  Measured on "cafe in Clifton, Karachi" (24 leads, emails on):

  | Setting | Leads per minute |
  |---|---|
  | Old version | ~8 |
  | Safe (1 tab) | ~12 |
  | **Fast (3 tabs)** | **~34** |
  | Max (4 tabs) | depends on the PC (5 tabs was slower than 3 in tests) |

## Notes

- **CAPTCHAs.** With the browser visible, the app waits up to 2 minutes for you to solve one. A solved CAPTCHA is remembered for later runs.
- **Blocks.** If Google keeps resetting connections or shows "unusual traffic", your IP is being rate-limited. Wait a few hours and run smaller batches.
- **Selectors.** Google changes its HTML from time to time. The Maps selectors are in the `SELECTORS` dict at the top of `scrapers/maps_scraper.py`.
- **Errors.** Full tracebacks go to `%LOCALAPPDATA%\Lead Scraper\scraper.log`.
- **Terms of use.** Automated access may break Google's Terms of Service. Collect only publicly listed business information, and follow the anti-spam laws that apply to your outreach (e.g. CAN-SPAM, GDPR).

## Project layout

```
main.py                    entry point ("smoke" argument: headless 2-lead self-test, result in the log)
gui/app.py                 main window: sidebar, stat cards, table, log
gui/theme.py               colours, fonts, cards, buttons, tables
gui/city_picker.py         country/city picker window
core/worker.py             background thread running the scraper (downloads Chromium on first use)
core/paths.py              where data, exports and the log are kept
core/browser_setup.py      first-run Chromium download
core/models.py             Lead dataclass, website classification, columns
core/exporter.py           CSV / XLSX export
core/history.py            lead history (no repeats across runs)
core/email_finder.py       emails from websites and web search
core/locations.py          countries, cities, big-city areas
core/geo.py                geocoding + map grid
scrapers/base.py           browser setup, search queue, filters, CAPTCHA handling
scrapers/maps_scraper.py   Google Maps scraping
assets/app.ico             app icon
tools/build.ps1            build + install the desktop app, make dist/Lead Scraper.zip
tools/copy_deps.py         copies only the packages the app needs into the app folder
tools/launcher.py          starts the app when Lead Scraper.exe is opened (becomes app/sitecustomize.py)
tools/installer.iss        Inno Setup script for dist/Lead Scraper Setup.exe
tools/uninstall.ps1        uninstaller used by Settings > Apps (runs with signed PowerShell)
```
