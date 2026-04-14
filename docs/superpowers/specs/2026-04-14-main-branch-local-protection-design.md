# Main Branch Local Protection Design

## Goal

Prevent accidental direct `git commit` and `git push` operations on `main` in a
way that is lightweight, repository-owned, and easy to understand.

## Chosen Approach

Use repo-local git hooks under `.githooks/` and activate them in each clone with
`git config core.hooksPath .githooks`.

This keeps the policy versioned with the repository without introducing new
runtime dependencies or changing the Python product surface.

## Behavior

- `.githooks/pre-commit` rejects commits when the current branch is `main`.
- `.githooks/pre-push` rejects any push whose destination ref is
  `refs/heads/main`.
- Detached HEAD states are not blocked by the commit hook.
- The hooks are advisory local protection and can still be bypassed with normal
  git escape hatches such as `--no-verify`; remote branch protection remains the
  authoritative enforcement layer.

## Documentation Impact

Record the hook location and activation requirement in `AGENTS.md` so future
agents know where the local policy lives and why it may appear inactive in a new
clone.

## Validation

- Mark both hook files executable.
- Set `core.hooksPath` to `.githooks` in the current clone.
- Run repository lint, tests, and guards after the change.
