# Task Input Design

Design inputs for the user who will rerun the task, not for the agent who
explored it once.

## Default Rule

Expose only the inputs users actually care about. Keep exploration knobs as
internal defaults unless they are likely to matter during normal reruns.

## Usually User-Facing

- target URL, query, or identifier
- output path or destination
- output filename or overwrite behavior
- filters, scope, date range, or count limits
- explicit profile selection only if users really need to choose it

## Usually Internal

- wait loops
- retry counts
- polling intervals
- exploration timeouts
- transient recovery toggles

Tune these during exploration, then encode stable defaults in `task.py`.

## Good Defaults

If the user did not specify a value but a sensible default improves usability,
choose one and document it in metadata.

Good examples:

- default download path in the task artifacts directory
- filename derived from a stable content identifier

Bad examples:

- exposing `wait_rounds`, `wait_seconds`, or similar knobs by default just because the agent used them during exploration

## Metadata Expectations

Record these in `task.meta.json`:

- which inputs are user-facing
- which defaults were chosen for rerun stability
- which internal knobs remain hidden and why

The goal is a task that feels obvious to run later, not a transcript of the
exploration process.
