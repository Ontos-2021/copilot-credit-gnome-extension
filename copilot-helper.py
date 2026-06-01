#!/usr/bin/env python3
"""GitHub Copilot billing usage helper for GNOME Shell extension."""
import json, os, re, subprocess, sys, time, urllib.request, urllib.error

NOW = time.gmtime()
YEAR, MONTH = NOW.tm_year, NOW.tm_mon
CONFIG_DIR = os.path.expanduser("~/.config/copilot-credit")
SELECTED_FILE = os.path.join(CONFIG_DIR, "selected_account")
QUOTAS_FILE = os.path.join(CONFIG_DIR, "quotas.json")
DEFAULT_TOTALS = {"requests": 1500, "credits": 1500}

def find_gh():
    for path in [os.path.expanduser("~/.local/bin/gh"), "gh"]:
        try:
            r = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=2)
            if r.returncode == 0:
                return path
        except Exception:
            pass
    return None

def get_token(user=None):
    gh = find_gh()
    if gh:
        try:
            cmd = [gh, "auth", "token"]
            if user:
                cmd.extend(["--user", user])
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except Exception:
            pass
    for var in ["GH_TOKEN", "GITHUB_TOKEN"]:
        if var in os.environ:
            return os.environ[var]
    return None

def list_accounts():
    gh = find_gh()
    if not gh:
        return None
    try:
        r = subprocess.run([gh, "auth", "status"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            return None
        accounts = []
        current = None
        for line in r.stdout.split("\n"):
            s = line.strip()
            m = re.search(r"Logged in to \S+ account (\S+)", s)
            if m:
                current = m.group(1)
            m = re.search(r"Active account:\s*(true|false)", s)
            if m and current:
                accounts.append({"username": current, "active": m.group(1) == "true"})
                current = None
        return accounts or None
    except Exception:
        return None

def is_copilot_item(item):
    product = (item.get("product") or "").lower()
    sku = (item.get("sku") or "").lower()
    return "copilot" in product or "copilot" in sku

def as_number(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0

def compact_item(item):
    return {
        "product": item.get("product", ""),
        "sku": item.get("sku", ""),
        "unitType": item.get("unitType", ""),
        "grossQuantity": as_number(item.get("grossQuantity", item.get("quantity", 0))),
        "discountQuantity": as_number(item.get("discountQuantity", 0)),
        "netQuantity": as_number(item.get("netQuantity", 0)),
        "grossAmount": as_number(item.get("grossAmount", 0)),
        "discountAmount": as_number(item.get("discountAmount", 0)),
        "netAmount": as_number(item.get("netAmount", 0)),
        "date": item.get("date", ""),
    }

def api_get(path, token):
    url = f"https://api.github.com{path}"
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2026-03-10",
        "User-Agent": "copilot-credit-gnome-extension"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors='replace')
        return {"error": f"HTTP {e.code}: {e.reason}", "error_detail": body[:500]}
    except Exception as e:
        return {"error": str(e)}

def selected_account():
    try:
        with open(SELECTED_FILE) as f:
            value = f.read().strip()
            if value:
                return value
    except Exception:
        pass
    accounts = list_accounts()
    if accounts:
        for account in accounts:
            if account.get("active"):
                return account.get("username")
        return accounts[0].get("username")
    return None

def save_selected_account(username):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    with open(SELECTED_FILE, "w") as f:
        f.write(username.strip())

def quota_for(username, unit_type):
    key = "credits" if unit_type.startswith("credit") else "requests"
    quota = DEFAULT_TOTALS.get(key)
    try:
        with open(QUOTAS_FILE) as f:
            data = json.load(f)
        value = None
        if isinstance(data.get(username), dict):
            value = data[username].get(key) or data[username].get(unit_type)
        elif username in data:
            value = data[username]
        if value is None and isinstance(data.get("default"), dict):
            value = data["default"].get(key) or data["default"].get(unit_type)
        elif value is None:
            value = data.get("default")
        if value is not None:
            quota = as_number(value)
    except Exception:
        pass
    return quota if quota and quota > 0 else None

def save_quota(username, total, unit_type="requests"):
    os.makedirs(CONFIG_DIR, exist_ok=True)
    try:
        with open(QUOTAS_FILE) as f:
            data = json.load(f)
            if not isinstance(data, dict):
                data = {}
    except Exception:
        data = {}
    data.setdefault(username, {})
    if not isinstance(data[username], dict):
        data[username] = {}
    key = "credits" if unit_type.startswith("credit") else "requests"
    data[username][key] = as_number(total)
    with open(QUOTAS_FILE, "w") as f:
        json.dump(data, f, indent=2, sort_keys=True)

def output(payload):
    print(json.dumps(payload, indent=2, ensure_ascii=False))

def data(user_arg=None):
    token = get_token(user=user_arg)
    if not token:
        output({
            "ok": False,
            "error": "No GitHub token. Run: gh auth login",
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        })
        return

    user = api_get("/user", token)
    if "error" in user:
        output({"ok": False, "error": user["error"], "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        return

    username = user.get("login", "?")
    accounts = list_accounts()

    # Gather monthly data
    usage = api_get(f"/users/{username}/settings/billing/usage?year={YEAR}&month={MONTH}", token)
    summary = api_get(f"/users/{username}/settings/billing/usage/summary?year={YEAR}&month={MONTH}", token)
    premium = api_get(f"/users/{username}/settings/billing/premium_request/usage?year={YEAR}&month={MONTH}", token)

    errors = {}
    copilot_usage = []
    summary_items = []
    copilot_models = []

    if "error" in usage:
        errors["usage"] = usage["error"]
    elif isinstance(usage.get("usageItems"), list):
        for item in usage["usageItems"]:
            if is_copilot_item(item):
                copilot_usage.append(compact_item(item))

    if "error" in summary:
        errors["summary"] = summary["error"]
    elif isinstance(summary.get("usageItems"), list):
        for item in summary["usageItems"]:
            if is_copilot_item(item):
                summary_items.append(compact_item(item))

    if "error" in premium:
        errors["premium"] = premium["error"]
    elif isinstance(premium.get("usageItems"), list):
        for item in premium["usageItems"]:
            qty = as_number(item.get("grossQuantity", 0))
            if qty > 0:
                copilot_models.append({
                    "model": item.get("model", "unknown"),
                    "quantity": qty,
                    "amount": as_number(item.get("grossAmount", 0))
                })

    copilot_models.sort(key=lambda item: item["quantity"], reverse=True)

    total_quantity = sum(item["grossQuantity"] for item in summary_items)
    if total_quantity == 0:
        total_quantity = sum(item["quantity"] for item in copilot_models)
    if total_quantity == 0:
        total_quantity = sum(item["grossQuantity"] for item in copilot_usage)

    gross_amount = sum(item["grossAmount"] for item in summary_items)
    discount_amount = sum(item["discountAmount"] for item in summary_items)
    net_amount = sum(item["netAmount"] for item in summary_items)
    unit_type = "requests"
    if summary_items and summary_items[0].get("unitType"):
        unit_type = summary_items[0]["unitType"].lower()

    total_allowance = quota_for(username, unit_type)
    remaining_quantity = None
    percentage_used = None
    if total_allowance:
        remaining_quantity = max(total_allowance - total_quantity, 0)
        percentage_used = min((total_quantity / total_allowance) * 100, 999)

    result = {
        "ok": True,
        "username": username,
        "accounts": accounts,
        "selected_account": user_arg or username,
        "period": f"{YEAR}-{MONTH:02d}",
        "unit_type": unit_type,
        "total_quantity": round(total_quantity, 2),
        "total_allowance": round(total_allowance, 2) if total_allowance else None,
        "remaining_quantity": round(remaining_quantity, 2) if remaining_quantity is not None else None,
        "percentage_used": round(percentage_used, 1) if percentage_used is not None else None,
        "total_premium_requests": round(total_quantity),
        "gross_amount": round(gross_amount, 4),
        "discount_amount": round(discount_amount, 4),
        "net_amount": round(net_amount, 4),
        "summary_items": summary_items,
        "daily_items": copilot_usage[-10:],
        "models": copilot_models,
        "errors": errors if errors else None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    }
    output(result)

def main():
    args = sys.argv[1:]

    if "--list-accounts" in args:
        accounts = list_accounts()
        output({"ok": bool(accounts), "accounts": accounts or [], "selected_account": selected_account()})
        return

    if "--selected" in args:
        selected = selected_account()
        output({"ok": bool(selected), "selected_account": selected})
        return

    if "--switch" in args:
        index = args.index("--switch")
        if index + 1 >= len(args):
            output({"ok": False, "error": "--switch requires a username"})
            return
        save_selected_account(args[index + 1])
        output({"ok": True, "selected_account": args[index + 1]})
        return

    if "--set-total" in args:
        index = args.index("--set-total")
        if index + 2 >= len(args):
            output({"ok": False, "error": "--set-total requires username and total"})
            return
        unit_type = "requests"
        if "--unit" in args:
            unit_index = args.index("--unit")
            if unit_index + 1 < len(args):
                unit_type = args[unit_index + 1]
        save_quota(args[index + 1], args[index + 2], unit_type=unit_type)
        output({"ok": True, "username": args[index + 1], "total_allowance": as_number(args[index + 2]), "unit_type": unit_type})
        return

    user_arg = None
    for index, arg in enumerate(args):
        if arg == "--user" and index + 1 < len(args):
            user_arg = args[index + 1]

    if not user_arg:
        user_arg = selected_account()
    data(user_arg=user_arg)

if __name__ == "__main__":
    main()
