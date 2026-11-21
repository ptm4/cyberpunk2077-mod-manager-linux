# GitHub settings for the maintainer

These keep the project open while every change to `main` still goes through the maintainer.
They have to be set by hand on github.com: Settings is only visible to the repository owner.

## 1. Make the repository public

**Settings → General → Danger Zone → Change visibility → Public.**

## 2. Protect `main` with a ruleset

**Settings → Rules → Rulesets → New ruleset → New branch ruleset.**

| Field | Value |
| --- | --- |
| Ruleset name | `Protect main` |
| Enforcement status | **Active** |
| Bypass list | **Add bypass → Repository admin**, then set it to **For pull requests only** |
| Target branches | **Add target → Include default branch** |

Tick these rules:

- **Restrict deletions**
- **Block force pushes**
- **Require a pull request before merging**, with:
  - Required approvals: **1**
  - **Dismiss stale pull request approvals when new commits are pushed**
  - **Require review from Code Owners**
  - **Require conversation resolution before merging**

Leave the other rules off. Press **Create**.

Why the bypass: GitHub never lets you approve your own pull request, so without it you could not merge your own work.
"For pull requests only" means you still go through a pull request (no direct pushes to `main`), and you are the only
one who can merge without someone else's approval. Everyone else needs your approval, because `.github/CODEOWNERS`
makes you the owner of every file.

Your own workflow from then on:

```bash
git switch -c my-change
git commit -s -m "..."
git push -u origin my-change
```

Then open the pull request on GitHub and merge it there.

## 3. Check sign-offs automatically (optional, recommended)

Install the free **DCO** GitHub App (github.com/apps/dco) on this repository. It marks a pull request red when a commit
lacks a `Signed-off-by` line. Once it has run on one pull request, add it to the ruleset: **Require status checks to
pass → Add checks → DCO**.

## 4. Smaller settings

- **Settings → General → Pull Requests:** keep **Allow squash merging**, untick merge commits and rebase merging, and
  tick **Always suggest updating pull request branches** and **Automatically delete head branches**.
- **Settings → General → Features:** keep **Issues** on. Turn on **Discussions** if you want questions kept apart from bug reports.
- **Settings → Actions → General → Fork pull request workflows:** **Require approval for all external contributors**
  (the project has no workflows yet; this keeps it safe if one is added).
- **Settings → Code security:** turn on **Private vulnerability reporting**.
- **About** (the gear next to About on the main page): add the topics `cyberpunk-2077`, `mod-manager`, `linux`,
  `proton`, `steam`, `nexus-mods`, `gtk4`.

## Note about the old picture

The Cyberpunk 2077 artwork was removed from the files, but it is still inside the earlier commits. Anyone can find it
in the history. Removing it from history means rewriting all commits and force-pushing, which also changes every
commit id. That is easiest now, before anyone else has cloned or forked the repository; later it breaks their copies.
It is optional, and the risk of leaving it is small.
