"""Automation module: CaptureVideo_Magento(...) records a browser scenario to .webm."""
import math
import os
import random
import re
import time

from playwright.sync_api import sync_playwright

PATH_TO_VIDEO_FOLDER = "./video"

HEADLESS = True
VIEWPORT = {"width": 1280, "height": 720}

SEARCH_BOX = 'textarea[name="q"]:visible, input[name="q"]:visible'
SEARCH_BUTTON = 'form button[type="submit"]:visible'
FIRST_RESULT = 'a[data-testid="result-title-a"]'

_page = None                      # page used by ShowCallout
_cursor = {"x": 60.0, "y": 60.0}  # last known mouse position

# ---------------------------------------------------------------------------
# Injected JS: SVG cursor, yellow highlight, click ripple, callout.
# Plain IIFE, evaluated as-is by context.add_init_script.
# ---------------------------------------------------------------------------
_INIT_SCRIPT = r"""
(() => {
  if (window.top !== window) return;
  if (window.__fx) return;
  const NS = 'http://www.w3.org/2000/svg';
  const st = { x: -200, y: -200, shown: false };
  let root = null, hl = null, cur = null;

  function ensure() {
    if (root && root.isConnected) return true;
    if (!document.documentElement) return false;
    root = document.createElement('div');
    root.id = '__fx_root';
    root.style.cssText = 'position:fixed;left:0;top:0;width:100vw;height:100vh;' +
      'overflow:visible;pointer-events:none;z-index:2147483647;';

    hl = document.createElement('div');   // yellow circle, radius 32px, behind the arrow
    hl.style.cssText = 'position:absolute;left:0;top:0;width:64px;height:64px;' +
      'margin:-32px 0 0 -32px;border-radius:50%;background:rgba(255,230,0,0.35);' +
      'pointer-events:none;display:none;';

    cur = document.createElement('div');  // white arrow with black outline, ~32x32
    cur.style.cssText = 'position:absolute;left:0;top:0;width:32px;height:32px;' +
      'pointer-events:none;display:none;';
    const svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('width', '32');
    svg.setAttribute('height', '32');
    svg.setAttribute('viewBox', '0 0 32 32');
    svg.style.cssText = 'overflow:visible;pointer-events:none;';
    const path = document.createElementNS(NS, 'path');
    path.setAttribute('d', 'M2 2 L2 26 L8 20.5 L12.5 30 L17 28 L12.5 18.8 L21 18.8 Z');
    path.setAttribute('fill', '#ffffff');
    path.setAttribute('stroke', '#000000');
    path.setAttribute('stroke-width', '1.8');
    path.setAttribute('stroke-linejoin', 'round');
    svg.appendChild(path);
    cur.appendChild(svg);

    root.appendChild(hl);
    root.appendChild(cur);
    document.documentElement.appendChild(root);
    place(st.x, st.y);
    return true;
  }

  function place(x, y) {
    st.x = x; st.y = y;
    if (!root) return;
    const t = 'translate(' + x + 'px,' + y + 'px)';
    hl.style.transform = t;
    cur.style.transform = t;
    if (st.shown) { hl.style.display = 'block'; cur.style.display = 'block'; }
  }

  function ripple(x, y) {
    if (!ensure()) return;
    const r = document.createElement('div');
    r.style.cssText = 'position:absolute;left:' + x + 'px;top:' + y + 'px;width:32px;height:32px;' +
      'margin:-16px 0 0 -16px;border-radius:50%;box-sizing:border-box;' +
      'border:3px solid rgba(255,120,0,0.95);background:rgba(255,200,0,0.25);pointer-events:none;';
    root.appendChild(r);
    const a = r.animate(
      [{ transform: 'scale(0.1)', opacity: 1 }, { transform: 'scale(1)', opacity: 0 }],
      { duration: 600, easing: 'ease-out' });
    a.onfinish = () => r.remove();
  }

  function callout(text, bg, color, fadeMs, holdMs) {
    return new Promise((resolve) => {
      if (!ensure()) { resolve(); return; }
      const d = document.createElement('div');
      d.textContent = text;
      d.style.cssText = 'position:fixed;left:50%;bottom:48px;transform:translateX(-50%);' +
        'width:max-content;max-width:80vw;padding:12px 22px;box-sizing:border-box;' +
        'border:2px solid #000;border-radius:6px;font:16pt/1.3 Arial,Helvetica,sans-serif;' +
        'box-shadow:0 4px 14px rgba(0,0,0,0.35);pointer-events:none;opacity:0;';
      d.style.background = bg;
      d.style.color = color;
      root.appendChild(d);
      const fin = d.animate([{ opacity: 0 }, { opacity: 1 }], { duration: fadeMs, fill: 'forwards' });
      fin.onfinish = () => {
        setTimeout(() => {
          resolve();  // fade-out continues in the background
          const fout = d.animate([{ opacity: 1 }, { opacity: 0 }], { duration: fadeMs, fill: 'forwards' });
          fout.onfinish = () => d.remove();
        }, holdMs);
      };
    });
  }

  window.__fx = { ensure, place, ripple, callout };

  window.addEventListener('mousemove', (e) => {
    st.shown = true;
    ensure();
    place(e.clientX, e.clientY);
  }, true);
  window.addEventListener('mousedown', (e) => {
    st.shown = true;
    ensure();
    place(e.clientX, e.clientY);
    ripple(e.clientX, e.clientY);
  }, true);
  setInterval(ensure, 300);  // re-attach if the page rebuilds <html>
})();
"""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def ShowCallout(text, bgColor="#FFEB3B", textColor="#000000", fade=2.0, hold=1.5, page=None):
    """Show a callout (yellow box, black 16pt text). `fade` and `hold` in seconds.
    Blocks for fade-in + hold; the fade-out runs in the background."""
    page = page or _page
    if page is None:
        return
    try:
        page.evaluate(
            "([t, b, c, f, h]) => window.__fx && window.__fx.callout(t, b, c, f, h)",
            [text, bgColor, textColor, int(fade * 1000), int(hold * 1000)],
        )
    except Exception as e:  # e.g. navigation destroyed the context - not critical
        print(f"  (callout skipped: {str(e).splitlines()[0]})")


def _move_to(page, x, y, duration=None):
    """Glide the mouse along a slightly curved path with ease-in-out (no teleporting)."""
    x0, y0 = _cursor["x"], _cursor["y"]
    dist = math.hypot(x - x0, y - y0)
    if dist < 1:
        page.mouse.move(x, y)
        return
    if duration is None:
        duration = min(1.6, 0.5 + dist / 1200.0)
    steps = max(25, min(120, int(dist / 6)))
    # control point offset perpendicular to the line -> gentle arc
    nx, ny = -(y - y0) / dist, (x - x0) / dist
    off = random.uniform(-0.08, 0.08) * dist
    cx, cy = (x0 + x) / 2 + nx * off, (y0 + y) / 2 + ny * off
    for i in range(1, steps + 1):
        t = i / steps
        e = t * t * (3 - 2 * t)  # smoothstep
        px = (1 - e) ** 2 * x0 + 2 * (1 - e) * e * cx + e ** 2 * x
        py = (1 - e) ** 2 * y0 + 2 * (1 - e) * e * cy + e ** 2 * y
        page.mouse.move(px, py)
        time.sleep(duration / steps)
    _cursor["x"], _cursor["y"] = x, y


def _click_at(page, x, y):
    _move_to(page, x, y)
    time.sleep(0.15)
    page.mouse.click(x, y, delay=90)  # real mousedown -> ripple


def _wait_box(page, selector, timeout=30.0):
    """Poll until the first match of selector is visible; return its bounding box."""
    end = time.time() + timeout
    last_err = None
    while time.time() < end:
        try:
            loc = page.locator(selector).first
            if loc.is_visible():
                box = loc.bounding_box()
                if box and box["width"] > 0 and box["height"] > 0:
                    return box
        except Exception as e:  # navigation in progress, context destroyed, etc.
            last_err = e
        time.sleep(0.3)
    raise TimeoutError(f"element not found: {selector} ({last_err})")


def _wait_results(page, timeout=60.0):
    """Wait for the results page (full navigation + client-side rendering, can be slow)."""
    end = time.time() + timeout
    while time.time() < end:
        try:
            if page.locator(FIRST_RESULT).count() > 0 and page.locator(FIRST_RESULT).first.is_visible():
                return
        except Exception:
            pass  # "Execution context was destroyed" during navigation - keep polling
        time.sleep(0.5)
    raise TimeoutError("search results did not appear")


def _human_type(page, text):
    for ch in text:
        page.keyboard.type(ch)
        delay = random.uniform(0.06, 0.18)
        if ch == " ":
            delay += random.uniform(0.05, 0.15)
        time.sleep(delay)


def _reshow_cursor(page):
    """After a navigation the new document has no cursor until the mouse moves."""
    try:
        page.mouse.move(_cursor["x"] + 1, _cursor["y"] + 1)
        page.mouse.move(_cursor["x"], _cursor["y"])
    except Exception:
        pass


def _safe_filename(name):
    name = re.sub(r'[\\/:*?"<>|\r\n\t]+', "_", name or "").strip(" .")
    return name or "video"


# ---------------------------------------------------------------------------
# Scenario
# ---------------------------------------------------------------------------
def _scenario(page, url, city):
    global _page
    _page = page
    _cursor["x"], _cursor["y"] = 60.0, 60.0

    if not re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", url):
        url = "https://" + url

    # 1. open page
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.mouse.move(_cursor["x"], _cursor["y"])  # 2. cursor appears
    time.sleep(1.0)
    ShowCallout("Opening the search engine", fade=1.0, hold=1.0)

    # 3. glide to search box and click it
    box = _wait_box(page, SEARCH_BOX, timeout=30)
    _click_at(page, box["x"] + min(box["width"] / 2, 200), box["y"] + box["height"] / 2)
    time.sleep(0.4)

    # 4. type the query character by character
    ShowCallout("Typing the search query", fade=1.0, hold=0.8)
    _human_type(page, f"Magento developer in {city}".strip())
    time.sleep(0.6)

    # 5. click the search button (fallback: Enter)
    try:
        btn = _wait_box(page, SEARCH_BUTTON, timeout=5)
        _click_at(page, btn["x"] + btn["width"] / 2, btn["y"] + btn["height"] / 2)
    except TimeoutError:
        page.keyboard.press("Enter")

    # 6. wait for results (navigation destroys the JS context - polling handles it)
    _wait_results(page, timeout=60)
    time.sleep(0.8)
    _reshow_cursor(page)
    ShowCallout("Results loaded - opening the first one", fade=1.0, hold=1.0)

    # 7. glide to the first result and click it
    page.locator(FIRST_RESULT).first.scroll_into_view_if_needed(timeout=10000)
    time.sleep(0.3)
    rbox = _wait_box(page, FIRST_RESULT, timeout=15)
    _click_at(page, rbox["x"] + min(rbox["width"] / 2, 150), rbox["y"] + rbox["height"] / 2)

    try:
        page.wait_for_load_state("domcontentloaded", timeout=20000)
    except Exception:
        pass
    time.sleep(1.5)
    _reshow_cursor(page)
    time.sleep(3.0)  # let the target page be visible in the video


def CaptureVideo_Magento(
    url,
    company_name,
    language,
    country,
    postcode,
    city,
    street,
    house_no,
):
    """Record the sample scenario. Returns absolute path to .webm, or None on failure."""
    video_dir = os.path.abspath(PATH_TO_VIDEO_FOLDER)
    os.makedirs(video_dir, exist_ok=True)
    final_path = os.path.join(video_dir, _safe_filename(company_name) + ".webm")

    ctx_kwargs = dict(
        viewport=VIEWPORT,
        record_video_dir=video_dir,
        record_video_size=VIEWPORT,
    )
    if language and re.match(r"^[a-z]{2}(-[A-Za-z]{2})?$", language.strip()):
        ctx_kwargs["locale"] = language.strip()

    ok = False
    tmp_video = None
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=HEADLESS,
                args=["--disable-blink-features=AutomationControlled"],
            )
            context = browser.new_context(**ctx_kwargs)
            context.add_init_script(_INIT_SCRIPT)
            page = context.new_page()
            video = page.video
            try:
                _scenario(page, url, city)
                ok = True
            except Exception as e:
                print(f"  scenario error: {e}")
            finally:
                context.close()  # finalizes the video file
            try:
                tmp_video = video.path()
            except Exception as e:
                print(f"  cannot get video path: {e}")
            browser.close()
    except Exception as e:
        print(f"  playwright error: {e}")
        return None

    if tmp_video and os.path.exists(tmp_video):
        if ok:
            os.replace(tmp_video, final_path)
            return final_path
        try:
            os.remove(tmp_video)
        except OSError:
            pass
    return None
