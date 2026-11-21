# Contributing to Samurai Mod Manager

Thanks for wanting to help. Bug reports, test reports from other distributions and code are all welcome.

## Reporting a problem

Open an issue and include:

- your distribution and how the game is installed (Steam, Flatpak Steam, Heroic, Lutris);
- what you did and what happened;
- the text of the output pane in the window (it has a **Copy** button), or the command and its output.

A report that the manager works fine on your setup is useful too. Most of it has only been tested on CachyOS so far.

## Sending a change

1. Open an issue first for anything larger than a small fix, so we can agree on the approach before you put time in.
2. Fork the repository, make your change on a branch, and open a pull request against `main`.
3. Run the tests before you send it: `python3 -m unittest discover -s dev/tests`
   (they work in temporary folders with a fake game and touch nothing real).
4. Sign off every commit (see below).

Every pull request is reviewed by the maintainer, [@ptm4](https://github.com/ptm4), who decides what gets merged.
Nobody else can merge into `main`. Please don't take a slow review or a "no" personally: keeping the manager small and
predictable is a feature.

### What fits the project

- **The window holds no mod logic.** Every button runs the same `samurai-mm` command a user could type. A new feature
  is usually one engine command in `samurai_mm/engine.py` plus a small piece of a tab in `samurai_mm/ui/`.
- **Nothing is deleted outright and nothing is overwritten silently.** Removed mods go to `removed/`, replaced files
  are backed up, and anything that changes the game folder has a dry run.
- **Plain language** in messages and buttons. Say what happened and what to do next.
- **No network access** and no telemetry. The engine uses only the Python standard library.
- **No game assets** (art, music, text from Cyberpunk 2077) in the repository.
- New source files start with the same two-line license header as the existing ones.

`dev/README.md` explains how the code is laid out.

## Sign-off (Developer Certificate of Origin)

This project uses the [Developer Certificate of Origin](https://developercertificate.org/). By adding a
`Signed-off-by` line to a commit you state that you wrote the change, or otherwise have the right to submit it,
under the project's license. Git adds the line for you:

```bash
git commit -s -m "Describe the change"
```

It must carry your real name and an email address you use. Pull requests with unsigned commits cannot be merged.
To sign off commits you already made: `git rebase --signoff main`, then force-push your branch.

## License

Samurai Mod Manager is licensed under the GNU General Public License, version 3 or later (see `LICENSE`).
Your contributions are licensed the same way. You keep the copyright on what you write.
