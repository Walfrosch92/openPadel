// shutdown.js – Power-Button + Bestätigungsdialog für alle Seiten

(function () {
    const POWER_SVG = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
        <path d="M13 3h-2v10h2V3zm4.83 2.17-1.42 1.42A6.92 6.92 0 0 1 19 12c0 3.87-3.13 7-7 7s-7-3.13-7-7c0-1.98.81-3.77 2.1-5.07L5.67 5.5A8.93 8.93 0 0 0 3 12a9 9 0 0 0 18 0c0-2.74-1.23-5.18-3.17-6.83z"/>
    </svg>`;

    const CSS = `
        .sd-btn {
            background: rgba(220,53,69,0.15);
            border: 1.5px solid rgba(220,53,69,0.5);
            color: #fff;
            border-radius: 7px;
            width: 36px;
            height: 36px;
            display: flex;
            align-items: center;
            justify-content: center;
            cursor: pointer;
            position: absolute;
            right: 14px;
            top: 50%;
            transform: translateY(-50%);
            transition: background 0.2s, border-color 0.2s;
            padding: 0;
        }
        .sd-btn:hover { background: rgba(220,53,69,0.45); border-color: #dc3545; }
        /* Button in .header-actions (wifi_info) */
        .header-actions .sd-btn {
            position: static;
            transform: none;
        }
        .sd-overlay {
            display: none;
            position: fixed;
            inset: 0;
            background: rgba(0,0,0,0.6);
            z-index: 9999;
            align-items: center;
            justify-content: center;
        }
        .sd-overlay.show { display: flex; }
        .sd-dialog {
            background: #fff;
            border-radius: 16px;
            padding: 32px 28px 24px;
            max-width: 380px;
            width: 90%;
            text-align: center;
            box-shadow: 0 20px 60px rgba(0,0,0,0.4);
        }
        .sd-icon { font-size: 3em; margin-bottom: 12px; }
        .sd-title {
            font-size: 1.3em;
            font-weight: 700;
            color: #212529;
            margin-bottom: 10px;
            font-family: Arial, sans-serif;
        }
        .sd-warning {
            font-size: 0.95em;
            color: #6c757d;
            margin-bottom: 24px;
            font-family: Arial, sans-serif;
        }
        .sd-btns { display: flex; gap: 10px; justify-content: center; }
        .sd-cancel {
            padding: 10px 24px;
            border: 1.5px solid #6c757d;
            border-radius: 8px;
            background: #fff;
            color: #6c757d;
            font-size: 1em;
            cursor: pointer;
            font-family: Arial, sans-serif;
        }
        .sd-cancel:hover { background: #f8f9fa; }
        .sd-confirm {
            padding: 10px 24px;
            border: none;
            border-radius: 8px;
            background: #dc3545;
            color: #fff;
            font-size: 1em;
            font-weight: 600;
            cursor: pointer;
            font-family: Arial, sans-serif;
        }
        .sd-confirm:hover { background: #bb2d3b; }
    `;

    function tr(key, fallback) {
        if (typeof getTranslation === 'function') {
            return getTranslation(key) || fallback;
        }
        return fallback;
    }

    function injectStyles() {
        const s = document.createElement('style');
        s.textContent = CSS;
        document.head.appendChild(s);
    }

    function createModal() {
        const overlay = document.createElement('div');
        overlay.className = 'sd-overlay';
        overlay.id = 'sdOverlay';
        overlay.innerHTML = `
            <div class="sd-dialog">
                <div class="sd-icon">⏻</div>
                <div class="sd-title" data-i18n="common.shutdown_confirm">Wirklich herunterfahren?</div>
                <div class="sd-warning" data-i18n="admin.warning_shutdown">Das Herunterfahren stoppt alle Dienste und schaltet das System aus.</div>
                <div class="sd-btns">
                    <button class="sd-cancel" id="sdCancel" data-i18n="common.cancel">Abbrechen</button>
                    <button class="sd-confirm" id="sdConfirm" data-i18n="common.shutdown_yes">Ja, herunterfahren</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        document.getElementById('sdCancel').addEventListener('click', function () {
            overlay.classList.remove('show');
        });
        overlay.addEventListener('click', function (e) {
            if (e.target === overlay) overlay.classList.remove('show');
        });
        document.getElementById('sdConfirm').addEventListener('click', doShutdown);
    }

    function createButton() {
        const btn = document.createElement('button');
        btn.className = 'sd-btn';
        btn.title = 'System herunterfahren';
        btn.innerHTML = POWER_SVG;
        btn.addEventListener('click', function () {
            // Übersetzungen aktualisieren bevor Modal gezeigt wird
            const overlay = document.getElementById('sdOverlay');
            overlay.querySelectorAll('[data-i18n]').forEach(el => {
                const val = tr(el.getAttribute('data-i18n'), el.textContent);
                if (val) el.textContent = val;
            });
            overlay.classList.add('show');
        });
        return btn;
    }

    async function doShutdown() {
        const confirmBtn = document.getElementById('sdConfirm');
        confirmBtn.disabled = true;
        confirmBtn.textContent = '...';
        try {
            await fetch('/api/system/shutdown', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
        } catch (_) {}
        // Zeige "System heruntergefahren" Seite
        setTimeout(function () {
            document.body.innerHTML = `
                <div style="display:flex;flex-direction:column;justify-content:center;align-items:center;
                            height:100vh;background:linear-gradient(135deg,#1e88e5 0%,#1565c0 100%);
                            color:#fff;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;text-align:center;">
                    <img src="/poweroff.jpg" alt="openPadel"
                         style="max-width:280px;max-height:280px;margin-bottom:30px;border-radius:20px;box-shadow:0 10px 40px rgba(0,0,0,0.3);">
                    <div style="font-size:2em;font-weight:600;text-shadow:0 2px 10px rgba(0,0,0,0.3);">
                        System wurde heruntergefahren
                    </div>
                    <div style="font-size:1.1em;margin-top:12px;opacity:0.85;">
                        Sie können dieses Fenster schließen
                    </div>
                </div>`;
        }, 1500);
    }

    // Globale Funktion damit admin.html sie weiter nutzen kann
    window.shutdownSystem = function () {
        document.getElementById('sdOverlay').classList.add('show');
    };

    document.addEventListener('DOMContentLoaded', function () {
        injectStyles();
        createModal();

        const btn = createButton();

        // Einfache Nav (index, webcam, settings, admin, stats)
        const simpleNav = document.querySelector('nav.nav');
        if (simpleNav) {
            simpleNav.appendChild(btn);
            return;
        }

        // Header-Actions Nav (wifi_info)
        const headerActions = document.querySelector('.header-actions');
        if (headerActions) {
            headerActions.insertBefore(btn, headerActions.firstChild);
        }
    });
})();
