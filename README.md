# Copilot Credit GNOME Extension

GNOME Shell extension that shows GitHub Copilot billing usage in the top bar.

## Features

- Shows current monthly Copilot usage in the GNOME top bar.
- Uses GitHub billing API through `gh` authentication.
- Supports multiple GitHub accounts logged into GitHub CLI.
- Switches viewed account from the extension menu without changing the global active `gh` account.
- Shows model breakdown, covered amount, charged amount, and last refresh time.
- Refreshes automatically every 5 minutes and includes a manual refresh action.

## Requirements

- GNOME Shell 50
- Python 3
- GitHub CLI (`gh`)
- A GitHub token with the `user` scope for each account to inspect

## Install

```bash
./install.sh
```

Then log out and log back in so GNOME Shell discovers the extension.

Enable it if needed:

```bash
gnome-extensions enable copilot-credit@local
```

## GitHub Login

Authenticate with GitHub CLI:

```bash
gh auth login --web
gh auth refresh -h github.com -s user
```

For extra accounts, log in with `gh` and refresh the `user` scope for each one.

## Account Switching

The extension reads accounts from `gh auth status` and displays them under the `Account` submenu.

The selected account is persisted in:

```text
~/.config/copilot-credit/selected_account
```

No GitHub token is stored by this extension.

## Manual Test

```bash
python3 ~/.local/share/gnome-shell/extensions/copilot-credit@local/copilot-helper.py --list-accounts
python3 ~/.local/share/gnome-shell/extensions/copilot-credit@local/copilot-helper.py --user YOUR_USERNAME
```
