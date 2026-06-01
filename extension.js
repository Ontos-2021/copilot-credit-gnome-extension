import St from 'gi://St';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import GObject from 'gi://GObject';

import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

let indicator = null;

const CopilotIndicator = GObject.registerClass(
class CopilotIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'GitHub Copilot Usage', false);

        this._destroyed = false;
        this._refreshing = false;
        this._timeoutId = null;
        this._selectedAccount = null;
        this._accountItems = [];

        this._label = new St.Label({
            text: 'Copilot ...',
            style_class: 'copilot-credit-panel-label'
        });
        this.add_child(this._label);

        this._buildMenu();
        this._scheduleRefresh();
    }

    _buildMenu() {
        this._userItem = new PopupMenu.PopupMenuItem('User: ...', {reactive: false});
        this.menu.addMenuItem(this._userItem);
        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._accountsSubmenu = new PopupMenu.PopupSubMenuMenuItem('Account: ...');
        this.menu.addMenuItem(this._accountsSubmenu);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._premiumItem = new PopupMenu.PopupMenuItem('Copilot usage: ...', {reactive: false});
        this.menu.addMenuItem(this._premiumItem);

        this._billingItem = new PopupMenu.PopupMenuItem('Billing: ...', {reactive: false});
        this.menu.addMenuItem(this._billingItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        this._detailItem = new PopupMenu.PopupMenuItem('', {reactive: false});
        this.menu.addMenuItem(this._detailItem);

        this._timestampItem = new PopupMenu.PopupMenuItem('Updated: ...', {reactive: false});
        this.menu.addMenuItem(this._timestampItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        let refreshBtn = new PopupMenu.PopupMenuItem('Refresh Now');
        refreshBtn.connect('activate', () => this._refresh());
        this.menu.addMenuItem(refreshBtn);

        this._errorItem = new PopupMenu.PopupMenuItem('', {reactive: false});
        this._errorItem.actor.hide();
        this.menu.addMenuItem(this._errorItem);
    }

    _scheduleRefresh() {
        this._refresh();
        if (this._timeoutId) GLib.source_remove(this._timeoutId);
        this._timeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 300, () => {
            this._refresh();
            return GLib.SOURCE_CONTINUE;
        });
    }

    _refresh() {
        if (this._refreshing || this._destroyed) return;
        this._refreshing = true;

        let scriptPath = GLib.build_filenamev([
            GLib.get_home_dir(),
            '.local', 'share', 'gnome-shell', 'extensions',
            'copilot-credit@local', 'copilot-helper.py'
        ]);

        let argv = ['/usr/bin/python3', scriptPath];
        if (this._selectedAccount) argv.push('--user', this._selectedAccount);

        try {
            let proc = Gio.Subprocess.new(
                argv,
                Gio.SubprocessFlags.STDOUT_PIPE | Gio.SubprocessFlags.STDERR_PIPE
            );

            proc.communicate_utf8_async(null, null, (_proc, res) => {
                if (this._destroyed) return;
                this._refreshing = false;
                try {
                    let [ok, stdout, stderr_] = _proc.communicate_utf8_finish(res);
                    if (!ok || _proc.get_exit_status() !== 0) {
                        this._showError(stderr_ || 'Helper process failed');
                        return;
                    }
                    let data = JSON.parse(stdout);
                    if (data.ok) {
                        this._updateDisplay(data);
                    } else {
                        this._showError(data.error || 'Unknown error');
                    }
                } catch (e) {
                    this._showError(String(e));
                }
            });
        } catch (e) {
            this._refreshing = false;
            this._showError(String(e));
        }
    }

    _updateDisplay(data) {
        this._errorItem.actor.hide();

        this._selectedAccount = data.selected_account || data.username || this._selectedAccount;
        this._rebuildAccounts(data.accounts || [], this._selectedAccount);

        this._userItem.label.text = 'User: ' + (data.username || '?');

        let total = data.total_quantity ?? data.total_premium_requests ?? 0;
        let unitType = data.unit_type || 'requests';
        let suffix = unitType.startsWith('request') ? 'pr' : unitType.startsWith('credit') ? 'cr' : unitType;
        this._label.text = 'Copilot ' + this._formatNumber(total) + suffix;
        this._premiumItem.label.text = 'This month: ' + this._formatNumber(total) + ' ' + unitType;
        this._billingItem.label.text = 'Billing: $' + this._formatMoney(data.net_amount || 0)
            + ' charged, $' + this._formatMoney(data.discount_amount || 0) + ' covered';

        let detail = [];
        if (data.period) detail.push('Period: ' + data.period);
        if (data.models && data.models.length > 0) {
            for (let m of data.models) {
                detail.push(m.model + ': ' + this._formatNumber(m.quantity));
            }
        }
        if (data.errors) {
            for (let [ep, err] of Object.entries(data.errors)) {
                detail.push('WARN ' + ep + ': ' + String(err).slice(0, 60));
            }
        }
        if (detail.length === 0) detail.push('No Copilot usage data');
        this._detailItem.label.text = detail.join('\n');

        this._timestampItem.label.text = 'Updated: ' + (data.timestamp || '...');
    }

    _rebuildAccounts(accounts, selectedAccount) {
        this._accountsSubmenu.label.text = 'Account: ' + (selectedAccount || 'default');

        for (let item of this._accountItems) item.destroy();
        this._accountItems = [];

        if (!accounts || accounts.length === 0) {
            let item = new PopupMenu.PopupMenuItem('No gh accounts found', {reactive: false});
            this._accountsSubmenu.menu.addMenuItem(item);
            this._accountItems.push(item);
            return;
        }

        for (let account of accounts) {
            let username = account.username;
            let prefix = username === selectedAccount ? '> ' : '  ';
            let activeSuffix = account.active ? ' (gh active)' : '';
            let item = new PopupMenu.PopupMenuItem(prefix + username + activeSuffix);
            item.connect('activate', () => this._switchAccount(username));
            this._accountsSubmenu.menu.addMenuItem(item);
            this._accountItems.push(item);
        }
    }

    _switchAccount(username) {
        if (!username || username === this._selectedAccount) return;
        this._selectedAccount = username;
        this._saveSelectedAccount(username);
        this._label.text = 'Copilot ...';
        this._refreshing = false;
        this._refresh();
    }

    _saveSelectedAccount(username) {
        let dir = GLib.build_filenamev([GLib.get_home_dir(), '.config', 'copilot-credit']);
        let path = GLib.build_filenamev([dir, 'selected_account']);
        try {
            GLib.mkdir_with_parents(dir, 0o755);
            GLib.file_set_contents(path, username);
        } catch (e) {
            this._showError('Could not save account: ' + String(e));
        }
    }

    _formatNumber(value) {
        let n = Number(value || 0);
        if (Math.abs(n - Math.round(n)) < 0.01) return String(Math.round(n));
        return n.toFixed(2).replace(/0+$/, '').replace(/\.$/, '');
    }

    _formatMoney(value) {
        return Number(value || 0).toFixed(2);
    }

    _showError(msg) {
        this._label.text = 'Copilot x';
        this._errorItem.label.text = 'Error: ' + String(msg).slice(0, 120);
        this._errorItem.actor.show();
    }

    destroy() {
        this._destroyed = true;
        if (this._timeoutId) {
            GLib.source_remove(this._timeoutId);
            this._timeoutId = null;
        }
        super.destroy();
    }
});

export default class CopilotCreditExtension extends Extension {
    enable() {
        indicator = new CopilotIndicator();
        Main.panel.addToStatusArea('copilot-credit-indicator', indicator, 1, 'right');
    }

    disable() {
        if (indicator) {
            indicator.destroy();
            indicator = null;
        }
    }
}
