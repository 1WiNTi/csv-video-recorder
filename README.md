# CSV-driven Browser Automation Video Recorder

Reads `input.csv` and records a video of automated browser actions for each row:
opens DuckDuckGo, shows a custom SVG cursor, glides to the search box, types
"Magento developer in <city>" character by character, clicks search and opens
the first result. Effects: SVG cursor, yellow highlight, click ripple, callouts.

## Setup (once)

Run these two commands one after another:

```
pip install -r requirements.txt
```

```
python -m playwright install chromium
```

## Run

```
python capture_video.py --headed
```



## Files

- `capture_video.py` - reads the CSV (`;` delimiter, `"` qualifier) and calls the function for each row
- `qscript.py` - `CaptureVideo_Magento(...)`, `PATH_TO_VIDEO_FOLDER`, `ShowCallout(...)`
- `input.csv` - sample input
- `requirements.txt` - dependencies (Playwright)
