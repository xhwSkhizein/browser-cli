# Preflight And Runtime

Use this reference before exploration when task success may depend on the
execution environment as much as the browser steps.

## What to Prove

- `browser-cli` is callable
- `browser_cli` is importable
- the Python environment that will execute `task.py` is the same one you just validated
- Chrome and the `browser-cli` runtime are usable
- task-specific Python deps exist in that same environment
- the target profile assumptions are true: login state, cookies, locale, storage, output dir

## Minimum Checks

- `which browser-cli`
- `python -c 'import browser_cli; print(browser_cli.__file__)'`
- any extra task deps in the same Python, such as `requests`
- `browser-cli status`
- a writable artifacts directory

If the task will later be run by `browser-cli task run`, the automation service,
or plain Python, validate that exact entry environment now. Do not validate with
one interpreter and execute with another.

## Profile And Site Assumptions

Check these before you explore too far:

- does the site require login
- does the current browser profile already have the needed login or cookies
- does the site depend on geo, locale, or persistent storage
- does the task need the full browser cookie jar rather than just `document.cookie`

If the task needs a login state that is missing, stop and confirm rather than
inventing a fake path.

## Early-Stop Signals

Stop and confirm quickly when any of these are true:

- the task needs response bodies, CDP data, or another driver feature the runtime does not expose
- the task depends on a missing login state or profile assumption
- the validated Python environment is not the one that will run the task
- the browser runtime is healthy enough to open a page but not healthy enough to provide the needed signal

Do not hide these gaps behind repeated retries.

## Douyin Lesson

For signed Douyin detail requests, the stable path required:

- real browser navigation to mint signed request URLs
- the full browser cookie jar from `browser-cli cookies`
- replay with matching `Referer`, `User-Agent`, and csrf headers

Replaying the detail URL with only `document.cookie` returned HTTP `200` with
an empty body. That was a runtime assumption failure, not a retry problem.
