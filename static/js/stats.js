// stats.js – Statistik-Seite im Aufbau der App
//
// Vorlage ist lib/widgets/statistics_body.dart der Flutter-App: Übersicht,
// Spiel-Statistiken, Spielverlauf-Statistik, Teams (Rangliste + direkter
// Vergleich), Match-Verlauf und die Match-Details (Momentum, Kennzahlen,
// Punkteverlauf). Die Kennzahlen folgen lib/services/match_insights.dart,
// damit Web und App dieselben Werte zeigen.
//
// Datenquelle ist das App-Format von /api/history ("history": team_a, team_b,
// winner 'A'/'B'/null, sets, mode "<modus>|<format>", point_history).

(function () {
    const TEAMS_COLLAPSED = 5;
    const MOMENTUM_WINDOW = 8;

    let matches = [];          // älteste zuerst
    let gameStats = null;
    let modeNames = {};
    let modeRules = {};
    let lastSignature = null;
    let filter = {range: 'all', query: ''};
    let showAllTeams = false;
    let h2hPick = null;        // [nameX, nameY], sobald der Nutzer gewählt hat
    let openMatchId = null;

    const $ = id => document.getElementById(id);
    const plural = (key, count, one, other) =>
        tr(`${key}_${count === 1 ? 'one' : 'other'}`, count === 1 ? one : other, {count});
    const pct = v => v == null ? '–' : Math.round(v * 100) + '%';
    const pad = n => String(n).padStart(2, '0');

    // ── Formatierung (wie in der App) ───────────────────────────────────────

    function fmtOverview(secs, includeDays) {
        if (includeDays && secs >= 86400) {
            const d = Math.floor(secs / 86400), h = Math.floor((secs % 86400) / 3600);
            return h > 0 ? `${d}d ${h}h` : `${d}d`;
        }
        const m = Math.floor(secs / 60);
        return m >= 60 ? `${Math.floor(m / 60)}h ${m % 60}m` : `${m} Min.`;
    }

    function fmtMatchDuration(s) {
        const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = s % 60;
        if (h > 0) return `${h}h ${pad(m)}m`;
        if (m > 0) return `${m}m ${pad(sec)}s`;
        return `${sec}s`;
    }

    function fmtGameDuration(s) {
        const m = Math.floor(s / 60);
        return m === 0 ? `${s % 60}s` : `${m}m ${pad(s % 60)}s`;
    }

    function matchDate(match) {
        const d = match.timestamp ? new Date(match.timestamp) : null;
        return d && !isNaN(d.getTime()) ? d : null;
    }

    function fmtDate(d) {
        const lang = document.documentElement.lang || 'de';
        const day = d.toLocaleDateString(lang, {day: 'numeric', month: 'short', year: 'numeric'});
        return `${day} · ${pad(d.getHours())}:${pad(d.getMinutes())}`;
    }

    function modeName(match) {
        const [id, format] = String(match.mode || '').split('|');
        const formats = {best_of_5: 'Best of 5', single_set: 'Single Set'};
        let name = modeNames[id];
        if (!name) {
            const stripped = (id.startsWith('custom_') ? id.slice(7) : id).replace(/_/g, ' ').trim();
            name = stripped ? stripped[0].toUpperCase() + stripped.slice(1) : '';
        }
        return `${name}, ${formats[format] || 'Best of 3'}`;
    }

    const setsWon = (match, side) => match.sets.filter(s =>
        side === 'A' ? s.score_a > s.score_b : s.score_b > s.score_a).length;
    const winnerName = match => match.winner === 'A' ? match.team_a
        : match.winner === 'B' ? match.team_b : null;
    const hasHistory = match => !!(match.point_history && (match.point_history.sets || [])
        .some(s => (s.games || []).length > 0 || (s.unknown_games || 0) > 0));
    const isBreak = g => !g.tb && g.w && g.s && g.w !== g.s;

    // ── Kennzahlen aus dem Punkteverlauf (match_insights.dart) ───────────────

    function gameWinner(a, b, rules) {
        const suddenDeath = !!rules.golden_point || rules.advantage === false;
        const need = suddenDeath ? 1 : 2;
        if (a >= 4 && a - b >= need) return 'A';
        if (b >= 4 && b - a >= need) return 'B';
        return null;
    }

    function insights(match) {
        if (!hasHistory(match)) return null;
        const rules = modeRules[String(match.mode || '').split('|')[0]] || {};
        const team = () => ({points: 0, serviceGames: 0, held: 0, breaks: 0,
            breakPoints: 0, breakPointsWon: 0, loveGames: 0, longestStreak: 0});
        const r = {A: team(), B: team(), deuceGames: 0, countedGames: 0};
        let streakTeam = null, streak = 0;

        for (const set of match.point_history.sets) {
            for (const g of set.games || []) {
                const points = g.p || [];
                for (const p of points) {
                    if (!r[p]) continue;
                    r[p].points++;
                    streak = p === streakTeam ? streak + 1 : 1;
                    streakTeam = p;
                    if (streak > r[p].longestStreak) r[p].longestStreak = streak;
                }
                if ((g.u || 0) > 0) { streakTeam = null; streak = 0; }

                if (!g.w || (g.u || 0) > 0 || g.tb) continue;
                const server = g.s;
                if (server !== 'A' && server !== 'B') continue;
                const receiver = server === 'A' ? 'B' : 'A';
                r.countedGames++;
                r[server].serviceGames++;
                if (g.w === server) r[server].held++;
                if (isBreak(g)) r[receiver].breaks++;

                // Breakball: würde der Rückschläger mit diesem Punkt das Spiel gewinnen?
                let pa = 0, pb = 0, deuce = false;
                for (const p of points) {
                    const ra = pa + (receiver === 'A' ? 1 : 0), rb = pb + (receiver === 'B' ? 1 : 0);
                    if (gameWinner(ra, rb, rules) === receiver) {
                        r[receiver].breakPoints++;
                        if (p === receiver) r[receiver].breakPointsWon++;
                    }
                    if (p === 'A') pa++; else pb++;
                    if (pa >= 3 && pb >= 3) deuce = true;
                }
                if (deuce) r.deuceGames++;
                if ((g.w === 'A' ? pb : pa) === 0) r[g.w].loveGames++;
            }
        }
        return r;
    }

    // ── Teams (TeamStatistics) ───────────────────────────────────────────────

    const teamKey = name => String(name || '').trim().toLowerCase();

    function teamRecords(list) {
        const map = new Map();
        const ordered = [...list].sort((a, b) => (matchDate(a) || 0) - (matchDate(b) || 0));
        for (const m of ordered) {
            for (const side of ['A', 'B']) {
                const name = String(side === 'A' ? m.team_a : m.team_b || '').trim();
                if (!name) continue;
                if (!map.has(teamKey(name))) {
                    map.set(teamKey(name), {name, matches: 0, wins: 0, setsWon: 0, setsLost: 0, results: []});
                }
                const rec = map.get(teamKey(name));
                rec.matches++;
                if (m.winner === side) rec.wins++;
                rec.results.push(m.winner == null ? null : m.winner === side);
                for (const s of m.sets) {
                    const mine = side === 'A' ? s.score_a : s.score_b;
                    const theirs = side === 'A' ? s.score_b : s.score_a;
                    if (mine > theirs) rec.setsWon++;
                    if (theirs > mine) rec.setsLost++;
                }
            }
        }
        return [...map.values()].sort((x, y) =>
            y.wins - x.wins || y.wins / y.matches - x.wins / x.matches);
    }

    function headToHead(list, teamX, teamY) {
        const h = {matches: 0, winsX: 0, winsY: 0, setsX: 0, setsY: 0};
        const kx = teamKey(teamX), ky = teamKey(teamY);
        for (const m of list) {
            const ka = teamKey(m.team_a), kb = teamKey(m.team_b);
            const xIsA = ka === kx && kb === ky, xIsB = kb === kx && ka === ky;
            if (!xIsA && !xIsB) continue;
            h.matches++;
            if (m.winner) {
                if ((m.winner === 'A') === xIsA) h.winsX++; else h.winsY++;
            }
            for (const s of m.sets) {
                const x = xIsA ? s.score_a : s.score_b, y = xIsA ? s.score_b : s.score_a;
                if (x > y) h.setsX++;
                if (y > x) h.setsY++;
            }
        }
        return h;
    }

    function mostFrequentPairing(list) {
        const count = {}, names = {};
        for (const m of list) {
            const ka = teamKey(m.team_a), kb = teamKey(m.team_b);
            if (!ka || !kb || ka === kb) continue;
            const k = ka < kb ? `${ka}|${kb}` : `${kb}|${ka}`;
            count[k] = (count[k] || 0) + 1;
            names[k] = [m.team_a.trim(), m.team_b.trim()];
        }
        const best = Object.keys(count).sort((a, b) => count[b] - count[a])[0];
        return best ? names[best] : null;
    }

    // ── Abschnitte ───────────────────────────────────────────────────────────

    const statCard = (gradient, iconName, title, value, full, delay) => `
        <div class="stat-card ${gradient}${full ? ' full' : ''}" style="animation-delay:${delay || 0}ms">
            ${icon(iconName)}
            <div><div class="t">${esc(title)}</div><div class="v">${esc(value)}</div></div>
        </div>`;

    function renderOverview() {
        const totalSets = matches.reduce((n, m) => n + m.sets.length, 0);
        const secs = matches.filter(m => m.duration_seconds).map(m => m.duration_seconds);
        const sum = secs.reduce((a, b) => a + b, 0);
        const counts = {};
        matches.forEach(m => { const n = modeName(m); counts[n] = (counts[n] || 0) + 1; });
        const mode = Object.keys(counts).sort((a, b) => counts[b] - counts[a])[0];

        let html = statCard('g-blue', 'trophy', tr('stats.matches', 'Matches'), matches.length)
            + statCard('g-mint', 'chart', tr('stats.sets', 'Sätze'), totalSets, false, 80);
        if (secs.length) {
            html += statCard('g-pink', 'clock', tr('stats.avg_duration', 'Ø Spieldauer'),
                    fmtOverview(Math.floor(sum / secs.length)), false, 160)
                + statCard('g-violet', 'hourglass', tr('stats.total_played', 'Gesamt gespielt'),
                    fmtOverview(sum, true), false, 240);
        }
        if (mode) html += statCard('g-gold', 'star', tr('stats.most_played_mode', 'Häufigster Modus'), mode, true, 300);
        $('overview').innerHTML = html;
    }

    function renderGameStats() {
        const g = gameStats;
        const show = !!(g && g.games && g.games.length);
        $('game-stats-section').classList.toggle('hidden', !show);
        if (!show) return;
        $('game-stats').innerHTML =
            statCard('g-mint', 'ball', tr('stats.total_games', 'Spiele gesamt'), g.total_games)
            + statCard('g-pink', 'clock', tr('stats.avg_duration', 'Ø Spieldauer'), fmtGameDuration(g.average_game_duration), false, 80)
            + statCard('g-blue', 'bolt', tr('stats.fastest_game', 'Schnellstes Spiel'), fmtGameDuration(g.shortest_game), false, 160)
            + statCard('g-gold', 'hourglass', tr('stats.longest_game', 'Längstes Spiel'), fmtGameDuration(g.longest_game), false, 240);
    }

    function renderInsights() {
        let serviceGames = 0, held = 0, bp = 0, bpWon = 0, deuce = 0, games = 0;
        let bestStreak = 0, bestStreakTeam = null, withHistory = 0;
        for (const m of matches) {
            const i = insights(m);
            if (!i) continue;
            withHistory++;
            for (const side of ['A', 'B']) {
                const t = i[side];
                serviceGames += t.serviceGames; held += t.held;
                bp += t.breakPoints; bpWon += t.breakPointsWon;
                if (t.longestStreak > bestStreak) {
                    bestStreak = t.longestStreak;
                    bestStreakTeam = side === 'A' ? m.team_a : m.team_b;
                }
            }
            deuce += i.deuceGames; games += i.countedGames;
        }
        $('insights-section').classList.toggle('hidden', withHistory === 0);
        if (!withHistory) return;
        const figure = (value, label) =>
            `<div class="figure"><div class="v">${esc(value)}</div><div class="l">${esc(label)}</div></div>`;
        const streakLabel = tr('stats.longest_streak', 'Längste Punkteserie');
        $('insights-based-on').textContent = plural('stats.insights_based_on', withHistory,
            'Aus 1 Match mit Punkteverlauf', 'Aus {count} Matches mit Punkteverlauf');
        $('insights').innerHTML =
            figure(pct(serviceGames ? held / serviceGames : null), tr('stats.hold_rate', 'Aufschlagspiele gehalten'))
            + figure(pct(bp ? bpWon / bp : null), tr('stats.break_point_rate', 'Breakbälle genutzt'))
            + figure(pct(games ? deuce / games : null), tr('stats.deuce_rate', 'Spiele mit Einstand'))
            + figure(bestStreak ? String(bestStreak) : '–',
                bestStreakTeam ? `${streakLabel} · ${bestStreakTeam}` : streakLabel);
    }

    function renderTeams() {
        const records = teamRecords(matches);
        const medals = ['#FFD66B', '#C0C6D4', '#CD8B5A'];
        const visible = showAllTeams ? records : records.slice(0, TEAMS_COLLAPSED);
        $('teams').innerHTML = visible.map((rec, i) => {
            const form = rec.results.slice(-5).map(won =>
                `<i class="${won === true ? 'w' : won === false ? 'l' : 'd'}"></i>`).join('');
            const record = tr('stats.team_record', '{wins} S · {losses} N · Sätze {setsWon}:{setsLost}', {
                wins: rec.wins, losses: rec.matches - rec.wins, setsWon: rec.setsWon, setsLost: rec.setsLost});
            return `
                <div class="team-row">
                    <div class="rank">${i < 3 ? `<span style="color:${medals[i]}">${icon('trophy')}</span>` : i + 1}</div>
                    <div class="who"><b>${esc(rec.name)}</b><span>${esc(record)}</span></div>
                    <div class="rate"><b>${pct(rec.wins / rec.matches)}</b><div class="form-dots">${form}</div></div>
                </div>`;
        }).join('');
        const toggle = $('teams-toggle');
        toggle.classList.toggle('hidden', records.length <= TEAMS_COLLAPSED);
        toggle.textContent = showAllTeams
            ? tr('stats.teams_show_less', 'Weniger anzeigen') : tr('stats.teams_show_all', 'Alle anzeigen');

        // Direkter Vergleich
        const names = records.map(r => r.name);
        const h2hCard = $('h2h-card');
        h2hCard.classList.toggle('hidden', names.length < 2);
        if (names.length < 2) return;
        const valid = pair => pair && pair.every(n => names.some(x => teamKey(x) === teamKey(n)))
            && teamKey(pair[0]) !== teamKey(pair[1]);
        const pair = valid(h2hPick) ? h2hPick : (mostFrequentPairing(matches) || [names[0], names[1]]);
        const options = selected => names.map(n =>
            `<option value="${esc(n)}"${teamKey(n) === teamKey(selected) ? ' selected' : ''}>${esc(n)}</option>`).join('');
        $('h2h-x').innerHTML = options(pair[0]);
        $('h2h-y').innerHTML = options(pair[1]);
        const h = headToHead(matches, pair[0], pair[1]);
        $('h2h-result').innerHTML = h.matches === 0
            ? `<p class="muted small center" style="margin-top:14px">${esc(tr('stats.h2h_none', 'Diese Teams haben noch nicht gegeneinander gespielt.'))}</p>`
            : `<div class="h2h-score"><span class="a">${h.winsX}</span><span class="sep">:</span><span class="b">${h.winsY}</span></div>
               <p class="muted small center">${esc(plural('stats.h2h_summary', h.matches,
                    '1 Match · Sätze {setsX}:{setsY}', '{count} Matches · Sätze {setsX}:{setsY}')
                    .replace('{setsX}', h.setsX).replace('{setsY}', h.setsY))}</p>`;
    }

    function filteredMatches() {
        const days = {week: 7, month: 30, year: 365}[filter.range];
        const since = days ? Date.now() - days * 86400000 : null;
        const q = filter.query.trim().toLowerCase();
        return matches.filter(m => {
            if (since) {
                const d = matchDate(m);
                if (!d || d.getTime() < since) return false;
            }
            return !q || m.team_a.toLowerCase().includes(q) || m.team_b.toLowerCase().includes(q);
        }).reverse();   // neueste zuerst
    }

    const miniSets = match => !match.sets.length ? '' : `
        <div class="mini-sets">
            <div>${match.sets.map(s => `<span class="mini-set${s.score_a > s.score_b ? ' a' : ''}">${s.score_a}</span>`).join('')}</div>
            <div>${match.sets.map(s => `<span class="mini-set${s.score_b > s.score_a ? ' b' : ''}">${s.score_b}</span>`).join('')}</div>
        </div>`;

    function renderHistory() {
        const list = filteredMatches();
        $('history-empty').classList.toggle('hidden', list.length > 0);
        $('history').innerHTML = list.map(m => {
            const winner = winnerName(m), d = matchDate(m);
            return `
                <div class="match-tile" role="button" tabindex="0" data-match="${esc(m.id)}">
                    <div class="top">
                        <div class="names">
                            <div class="a${m.winner === 'A' ? ' won' : ''}">${esc(m.team_a)}</div>
                            <div class="b${m.winner === 'B' ? ' won' : ''}">${esc(m.team_b)}</div>
                        </div>
                        <div class="score">
                            <b>${setsWon(m, 'A')}:${setsWon(m, 'B')}</b>
                            ${winner ? `<div class="winner ${m.winner === 'A' ? 'c-a' : 'c-b'}">${icon('trophy')}<span>${esc(winner)}</span></div>` : ''}
                        </div>
                    </div>
                    ${miniSets(m)}
                    <div class="mode">${icon('ball')}<span>${esc(modeName(m))}</span>${hasHistory(m) ? icon('insights') : ''}${icon('right')}</div>
                    <div class="meta">
                        ${m.duration_seconds ? `<span class="chip-time">${icon('clock')}${fmtMatchDuration(m.duration_seconds)}</span>` : ''}
                        ${d ? `<span>${icon('calendar')} ${esc(fmtDate(d))}</span>` : ''}
                        <span style="flex:1"></span>
                        <button class="icon-btn danger" data-delete="${esc(m.id)}" title="${esc(tr('stats.delete', 'Löschen'))}" style="width:32px;height:32px">${icon('trash')}</button>
                    </div>
                </div>`;
        }).join('');
    }

    // ── Match-Details ────────────────────────────────────────────────────────

    function momentumData(history) {
        const seq = [], setStarts = [], breaks = [];
        for (const set of history.sets) {
            if (seq.length) setStarts.push(seq.length);
            for (const g of set.games || []) {
                for (const p of g.p || []) seq.push(p === 'A' ? 1 : -1);
                if (isBreak(g) && (g.p || []).length) breaks.push(seq.length - 1);
            }
        }
        // 1) exponentiell gewichteter Anteil der letzten Punkte, 2) zentrierter
        // gleitender Mittelwert, 3) so skaliert, dass die stärkste Phase das
        // Diagramm füllt (ruhige Matches werden nicht aufgeblasen).
        const alpha = 2 / (MOMENTUM_WINDOW + 1), ema = [];
        let e = 0;
        for (const v of seq) { e += alpha * (v - e); ema.push(e); }
        const smooth = ema.map((_, i) => {
            let sum = 0, cnt = 0;
            for (let k = Math.max(0, i - 3); k <= Math.min(ema.length - 1, i + 3); k++) { sum += ema[k]; cnt++; }
            return sum / cnt;
        });
        const scale = 1 / Math.max(smooth.reduce((m, v) => Math.max(m, Math.abs(v)), 0), 0.5);
        return {values: smooth.map(v => Math.max(-1, Math.min(1, v * scale))), setStarts, breaks};
    }

    function momentumSvg(data, width) {
        const height = 150, n = data.values.length, mid = height / 2, amp = mid - 6;
        const x = i => n === 1 ? 0 : i / (n - 1) * width;
        const at = i => [x(i), mid - data.values[i] * amp];
        const step = Math.max(1, Math.ceil(n / (width / 6)));
        const nodes = [];
        for (let i = 0; i < n; i += step) nodes.push(at(i));
        if ((n - 1) % step !== 0) nodes.push(at(n - 1));
        const f = v => v.toFixed(1);

        // Glatte Kurve (Catmull-Rom → kubische Bézier-Segmente)
        let line = `M${f(nodes[0][0])},${f(nodes[0][1])}`;
        for (let i = 0; i < nodes.length - 1; i++) {
            const p0 = nodes[Math.max(i - 1, 0)], p1 = nodes[i], p2 = nodes[i + 1];
            const p3 = nodes[Math.min(i + 2, nodes.length - 1)];
            line += ` C${f(p1[0] + (p2[0] - p0[0]) / 6)},${f(p1[1] + (p2[1] - p0[1]) / 6)}`
                + ` ${f(p2[0] - (p3[0] - p1[0]) / 6)},${f(p2[1] - (p3[1] - p1[1]) / 6)} ${f(p2[0])},${f(p2[1])}`;
        }
        const area = `${line} L${f(nodes[nodes.length - 1][0])},${mid} L${f(nodes[0][0])},${mid} Z`;

        const starts = [0, ...data.setStarts];
        let grid = `<line x1="0" y1="${mid}" x2="${width}" y2="${mid}" stroke="var(--ink-faint)" stroke-width="1"/>`;
        starts.forEach((start, s) => {
            const sx = x(start), end = s + 1 < starts.length ? x(starts[s + 1]) : width;
            if (s > 0) grid += `<line x1="${f(sx)}" y1="0" x2="${f(sx)}" y2="${height}" stroke="var(--ink-faint)" stroke-dasharray="4 4"/>`;
            if (end - sx > 44) {
                grid += `<text x="${f(sx + 4)}" y="${height - 3}" font-size="10" font-weight="600" fill="var(--ink-dim)">${esc(tr('stats.set_n', 'Satz {n}', {n: s + 1}))}</text>`;
            }
        });
        const dots = data.breaks.map(b => {
            const p = at(b);
            return `<circle cx="${f(p[0])}" cy="${f(p[1])}" r="4.5" fill="#FFD66B" stroke="rgba(0,0,0,.35)"/>`;
        }).join('');

        return `
            <svg viewBox="0 0 ${width} ${height}" width="${width}" height="${height}">
                <defs>
                    <linearGradient id="mo-a" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0" stop-color="#0A84FF" stop-opacity=".75"/><stop offset="1" stop-color="#0A84FF" stop-opacity=".2"/>
                    </linearGradient>
                    <linearGradient id="mo-b" x1="0" y1="1" x2="0" y2="0">
                        <stop offset="0" stop-color="#BF5AF2" stop-opacity=".75"/><stop offset="1" stop-color="#BF5AF2" stop-opacity=".2"/>
                    </linearGradient>
                    <clipPath id="mo-top"><rect x="0" y="0" width="${width}" height="${mid}"/></clipPath>
                    <clipPath id="mo-bottom"><rect x="0" y="${mid}" width="${width}" height="${mid}"/></clipPath>
                </defs>
                ${grid}
                <path d="${area}" fill="url(#mo-a)" clip-path="url(#mo-top)"/>
                <path d="${area}" fill="url(#mo-b)" clip-path="url(#mo-bottom)"/>
                <path d="${line}" fill="none" stroke="var(--ink)" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                ${dots}
            </svg>`;
    }

    function keyFigures(match) {
        const i = insights(match);
        if (!i) return '';
        const a = i.A, b = i.B;
        const ratio = (x, n) => n === 0 ? '–' : `${x}/${n} · ${Math.round(x / n * 100)}%`;
        const row = (label, ta, tb, va, vb) => {
            const total = va + vb;
            return `
                <div class="cmp">
                    <div class="lbl"><span class="c-a">${esc(ta)}</span><span>${esc(label)}</span><span class="c-b">${esc(tb)}</span></div>
                    <div class="bar"><i class="a" style="flex:${total ? va / total : .5}"></i><i class="b" style="flex:${total ? vb / total : .5}"></i></div>
                </div>`;
        };
        const rate = t => t.serviceGames ? t.held / t.serviceGames : 0;
        return `
            <div class="card">
                <div class="card-title">${esc(tr('stats.key_figures', 'Kennzahlen'))}</div>
                ${row(tr('stats.points', 'Punkte'), a.points, b.points, a.points, b.points)}
                ${row(tr('stats.hold_rate', 'Aufschlagspiele gehalten'), ratio(a.held, a.serviceGames), ratio(b.held, b.serviceGames), rate(a), rate(b))}
                ${row(tr('stats.breaks', 'Breaks'), a.breaks, b.breaks, a.breaks, b.breaks)}
                ${row(tr('stats.break_point_rate', 'Breakbälle genutzt'), ratio(a.breakPointsWon, a.breakPoints), ratio(b.breakPointsWon, b.breakPoints), a.breakPointsWon, b.breakPointsWon)}
                ${row(tr('stats.love_games', 'Spiele zu null'), a.loveGames, b.loveGames, a.loveGames, b.loveGames)}
                ${row(tr('stats.longest_streak', 'Längste Punkteserie'), a.longestStreak, b.longestStreak, a.longestStreak, b.longestStreak)}
                <p class="muted small">${esc(i.deuceGames === 0 ? tr('stats.deuce_games_zero', 'Kein Spiel mit Einstand')
                    : plural('stats.deuce_games', i.deuceGames, '1 Spiel mit Einstand', '{count} Spiele mit Einstand'))}</p>
            </div>`;
    }

    function gameRow(game, index, runningScore) {
        const points = game.p || [], unknown = game.u || 0;
        let a = 0, b = 0;
        const label = (own, opp) => game.tb ? String(own)
            : own >= 3 && opp >= 3 ? (own > opp ? 'AD' : '40') : ['0', '15', '30', '40'][Math.min(own, 3)];
        let dots = unknown > 0 ? `<div class="dot"><i>+${unknown}</i><small></small></div>` : '';
        points.forEach((t, i) => {
            if (t === 'A') a++; else b++;
            const gamePoint = !!game.w && i === points.length - 1;
            const text = gamePoint || unknown > 0 ? '' : label(t === 'A' ? a : b, t === 'A' ? b : a);
            dots += `<div class="dot ${t === 'A' ? 'a' : 'b'}"><i>${gamePoint ? icon('check') : ''}</i><small>${text}</small></div>`;
        });
        const cls = t => t === 'A' ? 'c-a' : t === 'B' ? 'c-b' : 'muted';
        const badge = game.tb ? '<span class="badge">TB</span>'
            : isBreak(game) ? `<span class="badge">${icon('bolt')}${esc(tr('stats.break', 'Break'))}</span>`
            : !game.w ? `<span class="badge dim">${esc(tr('stats.unfinished', 'nicht beendet'))}</span>` : '';
        return `
            <div class="game-row">
                <div class="left">
                    <b class="${cls(game.w)}">${runningScore || '#' + index}</b>
                    ${game.s === 'A' || game.s === 'B' ? `<span class="${cls(game.s)}">${icon('ball')}</span>` : ''}
                    ${game.d != null ? `<small>${fmtGameDuration(game.d)}</small>` : ''}
                </div>
                <div class="dots">${dots}</div>
                ${badge}
            </div>`;
    }

    function setCard(match, set, number) {
        const score = match.sets[number - 1];
        const games = set.games || [], unknownGames = set.unknown_games || 0;
        const complete = unknownGames === 0 && games.every(g => !(g.u > 0));
        const count = team => games.reduce((n, g) => n + (g.p || []).filter(p => p === team).length, 0);
        const breaks = team => games.filter(g => isBreak(g) && g.w === team).length;
        const chip = (label, x, y) =>
            `<span class="chip">${esc(label)} <b class="c-a">${x}</b>:<b class="c-b">${y}</b></span>`;
        let ga = 0, gb = 0;
        const rows = games.map((g, i) => {
            if (g.w === 'A') ga++; else if (g.w === 'B') gb++;
            return gameRow(g, i + 1, unknownGames === 0 && g.w ? `${ga}:${gb}` : null);
        }).join('');
        return `
            <div class="card">
                <div class="set-head">
                    <b>${esc(tr('stats.set_n', 'Satz {n}', {n: number}))}</b>
                    ${complete ? chip(tr('stats.points', 'Punkte'), count('A'), count('B')) : ''}
                    ${chip(tr('stats.breaks', 'Breaks'), breaks('A'), breaks('B'))}
                    ${score ? `<span class="sc"><span class="c-a">${score.score_a}</span>:<span class="c-b">${score.score_b}</span></span>` : ''}
                </div>
                ${unknownGames > 0 ? `<p class="muted small">${esc(plural('stats.unknown_games', unknownGames,
                    '1 Spiel ohne Aufzeichnung', '{count} Spiele ohne Aufzeichnung'))}</p>` : ''}
                ${rows}
            </div>`;
    }

    function openDetail(id) {
        const match = matches.find(m => m.id === id);
        if (!match) return;
        openMatchId = id;
        const d = matchDate(match), winner = winnerName(match), history = hasHistory(match);
        const legend = `
            <div class="legend">
                <span class="c-a">${icon('ball')}</span><span class="c-b">${icon('ball')}</span><span>${esc(tr('stats.serve', 'Aufschlag'))}</span>
                <span class="badge">${icon('bolt')}${esc(tr('stats.break', 'Break'))}</span>
            </div>`;
        $('detail-body').innerHTML = `
            <div class="card">
                <div class="detail-score">
                    <div class="tn c-a">${esc(match.team_a)}</div>
                    <div class="big"><span class="c-a">${setsWon(match, 'A')}</span>:<span class="c-b">${setsWon(match, 'B')}</span></div>
                    <div class="tn c-b">${esc(match.team_b)}</div>
                </div>
                ${miniSets(match).replace('class="mini-sets"', 'class="mini-sets" style="display:flex;flex-direction:column;align-items:center"')}
                <div class="detail-meta">
                    ${winner ? `<span class="${match.winner === 'A' ? 'c-a' : 'c-b'}">${icon('trophy')} ${esc(winner)}</span>` : ''}
                    <span>${icon('ball')} ${esc(modeName(match))}</span>
                    ${match.duration_seconds ? `<span>${icon('clock')} ${fmtMatchDuration(match.duration_seconds)}</span>` : ''}
                    ${d ? `<span>${icon('calendar')} ${esc(fmtDate(d))}</span>` : ''}
                </div>
            </div>
            ${history ? `
                <div class="card momentum">
                    <div class="card-title" style="margin-bottom:2px">${esc(tr('stats.momentum', 'Momentum'))}</div>
                    <p class="muted small" style="margin-bottom:10px">${esc(tr('stats.momentum_hint', 'Wer wann dominiert hat'))}</p>
                    <div id="momentum-chart"></div>
                </div>
                ${keyFigures(match)}
                ${legend}
                ${match.point_history.sets.map((set, i) => setCard(match, set, i + 1)).join('')}`
            : `<div class="card center">
                    <div class="card-title" style="justify-content:center">${esc(tr('stats.no_history', 'Kein Punkteverlauf verfügbar'))}</div>
                    <p class="muted small">${esc(tr('stats.no_history_text', 'Für dieses Match wurde kein Punkteverlauf aufgezeichnet.'))}</p>
               </div>`}`;
        $('detail-overlay').classList.add('show');
        if (history) {
            const data = momentumData(match.point_history);
            const box = $('momentum-chart');
            if (data.values.length > 1) box.innerHTML = momentumSvg(data, Math.max(box.clientWidth, 240));
        }
    }

    function closeDetail() {
        openMatchId = null;
        $('detail-overlay').classList.remove('show');
    }

    // ── Laden & Aktionen ─────────────────────────────────────────────────────

    function render() {
        const empty = matches.length === 0;
        $('stats-content').classList.toggle('hidden', empty);
        $('stats-empty').classList.toggle('hidden', !empty);
        if (empty) return;
        renderOverview();
        renderGameStats();
        renderInsights();
        renderTeams();
        renderHistory();
    }

    async function loadModes() {
        try {
            const modes = await (await fetch('/api/game-modes')).json();
            modes.forEach(m => { modeNames[m.id] = m.name; });
            await Promise.all(modes.map(async m => {
                try {
                    modeRules[m.id] = (await (await fetch(`/api/game-modes/${encodeURIComponent(m.id)}`)).json()).rules || {};
                } catch (e) {}
            }));
        } catch (error) {
            console.error('Error loading game modes:', error);
        }
    }

    async function load() {
        try {
            const [history, stats] = await Promise.all([
                fetch('/api/history').then(r => r.json()),
                fetch('/api/game-stats').then(r => r.json()).catch(() => null),
            ]);
            const signature = JSON.stringify([history.history, stats]);
            if (signature === lastSignature) return;   // nichts Neues: Ansicht nicht neu aufbauen
            lastSignature = signature;
            matches = (history.history || []).map(m => ({...m, sets: m.sets || [],
                team_a: m.team_a || 'Team A', team_b: m.team_b || 'Team B'}));
            gameStats = stats;
            render();
            if (openMatchId && !matches.some(m => m.id === openMatchId)) closeDetail();
        } catch (error) {
            console.error('Error loading matches:', error);
            showStatus(tr('stats.load_error', 'Fehler beim Laden der Matches'), 'error');
        }
    }

    function showStatus(message, type) {
        const box = $('status-message');
        box.textContent = message;
        box.className = 'status-message status-' + type;
        box.style.display = 'block';
        setTimeout(() => { box.style.display = 'none'; }, 3000);
    }

    async function deleteMatch(id) {
        const ok = await confirmDialog(tr('stats.delete_title', 'Match löschen?'),
            tr('stats.delete_message', 'Dieses Match wird dauerhaft aus der Statistik entfernt.'),
            tr('stats.delete', 'Löschen'), true);
        if (!ok) return;
        try {
            const data = await (await fetch(`/api/history/${encodeURIComponent(id)}`, {method: 'DELETE'})).json();
            showStatus(data.status === 'success' ? tr('stats.deleted', 'Match gelöscht')
                : tr('stats.delete_error', 'Fehler beim Löschen'), data.status === 'success' ? 'success' : 'error');
            load();
        } catch (error) {
            showStatus(tr('stats.delete_error', 'Fehler beim Löschen'), 'error');
        }
    }

    async function clearAll() {
        const ok = await confirmDialog(tr('stats.clear_all', 'Alle Matches löschen') + '?',
            tr('stats.clear_all_message', 'Alle Matches werden gelöscht. Das kann nicht rückgängig gemacht werden.'),
            tr('stats.clear_all', 'Alle Matches löschen'), true);
        if (!ok) return;
        try {
            const data = await (await fetch('/api/history', {method: 'DELETE'})).json();
            showStatus(data.status === 'success' ? tr('stats.all_deleted', 'Alle Matches gelöscht')
                : tr('stats.delete_error', 'Fehler beim Löschen'), data.status === 'success' ? 'success' : 'error');
            load();
        } catch (error) {
            showStatus(tr('stats.delete_error', 'Fehler beim Löschen'), 'error');
        }
    }

    document.addEventListener('DOMContentLoaded', async function () {
        $('history').addEventListener('click', e => {
            const del = e.target.closest('[data-delete]');
            if (del) { e.stopPropagation(); deleteMatch(del.dataset.delete); return; }
            const tile = e.target.closest('[data-match]');
            if (tile) openDetail(tile.dataset.match);
        });
        $('history').addEventListener('keydown', e => {
            if (e.key === 'Enter' && e.target.matches('[data-match]')) openDetail(e.target.dataset.match);
        });
        $('filter-range').addEventListener('click', e => {
            const button = e.target.closest('button[data-range]');
            if (!button) return;
            filter.range = button.dataset.range;
            $('filter-range').querySelectorAll('button').forEach(b => b.classList.toggle('active', b === button));
            renderHistory();
        });
        $('filter-search').addEventListener('input', e => { filter.query = e.target.value; renderHistory(); });
        $('teams-toggle').addEventListener('click', () => { showAllTeams = !showAllTeams; renderTeams(); });
        const pickH2h = () => { h2hPick = [$('h2h-x').value, $('h2h-y').value]; renderTeams(); };
        $('h2h-x').addEventListener('change', pickH2h);
        $('h2h-y').addEventListener('change', pickH2h);
        $('clear-all-btn').addEventListener('click', clearAll);
        $('detail-close').addEventListener('click', closeDetail);
        $('detail-overlay').addEventListener('click', e => { if (e.target === $('detail-overlay')) closeDetail(); });
        document.addEventListener('keydown', e => { if (e.key === 'Escape') closeDetail(); });

        await loadModes();
        await load();
        setInterval(load, 10000);
    });
})();
