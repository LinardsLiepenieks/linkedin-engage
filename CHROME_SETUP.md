# Chrome setup (remote debugging)

The scripts **attach to a debug-enabled Chrome over the DevTools protocol** instead of
launching a fresh automated browser. This keeps a normal session, cookies, TLS fingerprint,
and `navigator.webdriver = false` — dramatically less detectable than a bot browser, and your
password is never touched.

## The easy way (automated — what the skill uses)

```bash
bash scripts/start_chrome.sh
```

This launches a **separate** Chrome instance with a dedicated profile
(`~/.chrome-linkedin-profile`) and debugging on, opens your LinkedIn feed, and **leaves your
everyday Chrome and its tabs alone**. It's idempotent — safe to run when Chrome's already up.

- **First run only:** log into LinkedIn in the window it opens. The dedicated profile then
  stays logged in for future runs.
- Prefer using your everyday, already-logged-in Chrome instead (this **closes your current
  tabs**)? Run `bash scripts/start_chrome.sh --main-profile`.

Everything below is the **manual equivalent**, for reference or troubleshooting.

---

## Manual launch

## macOS

**1. Fully quit Chrome first** (⌘Q — not just closing the window).

**2. Relaunch it with the debugging flag.** Run this in a terminal:

```bash
/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
  --remote-debugging-port=9222 \
  --user-data-dir="$HOME/.chrome-linkedin-profile"
```

> The `--user-data-dir` points at a **dedicated profile** so this debugging instance is
> isolated from your everyday Chrome. The **first time**, log into LinkedIn in this window.
> After that the profile stays logged in and you just rerun the command.

If you'd rather use your **main** profile (already logged in everywhere), omit
`--user-data-dir` — but then you must have *all* other Chrome windows quit first, or
Chrome ignores the debugging flag.

**3. Leave that Chrome window open.** Open your LinkedIn feed tab in it. The scripts
connect to `http://localhost:9222`.

## Verify it's working

```bash
curl -s http://localhost:9222/json/version
```

You should see a JSON blob with your Chrome version. If you get "connection refused",
Chrome isn't running with the flag (usually because another Chrome instance was already
open when you launched it).

## Tip: make it a shortcut

Add to your `~/.zshrc`:

```bash
alias chrome-debug='/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome --remote-debugging-port=9222 --user-data-dir="$HOME/.chrome-linkedin-profile"'
```

Then just run `chrome-debug` before a session.
