# Install Browser CLI Skills

`browser-cli install-skills` copies the packaged Browser CLI skills from the
installed distribution into a skills directory on your machine.

Use it when you want an agent runtime to discover the Browser CLI skills
without pointing that runtime at this repository checkout.

## What the command installs

Browser CLI currently ships exactly three packaged skills:

- `browser-cli-converge`
- `browser-cli-delivery`
- `browser-cli-explore`

Those skills live inside the installed wheel. The command does not scan your
repository checkout for loose files. It copies the packaged skill directories
that were published with the installed Browser CLI version.

## Default install path

Run the command with no extra flags:

```bash
browser-cli install-skills
```

Browser CLI installs the packaged skills into:

```text
~/.agents/skills
```

After the command finishes, you should see three directories under that target,
one for each packaged skill.

## Preview before writing files

Use `--dry-run` when you want to check what Browser CLI would install without
modifying the target directory:

```bash
browser-cli install-skills --dry-run
```

That mode is useful when you are checking paths on a new machine or when you
want to confirm whether Browser CLI will install new directories or update
existing ones.

## Choose a different target

Use `--target` when your agent runtime reads skills from a different root:

```bash
browser-cli install-skills --target ~/.codex/skills
```

Browser CLI treats the `--target` path as the skills root. It creates the
directory if needed, then writes one subdirectory per packaged skill.

## What happens on rerun

You can rerun `install-skills` safely.

If the target already contains one of the packaged Browser CLI skill
directories, Browser CLI replaces that directory with the packaged version from
the installed distribution. This lets you refresh the installed skills after
you upgrade Browser CLI.

## A typical flow

If you installed Browser CLI with `uv`, a common sequence looks like this:

```bash
uv tool install browser-control-and-automation-cli
browser-cli doctor
browser-cli install-skills --dry-run
browser-cli install-skills
browser-cli read https://example.com
```

That sequence checks the machine first, previews the skill install, installs
the packaged skills, then verifies that Browser CLI itself can open and read a
page.
