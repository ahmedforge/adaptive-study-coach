// Tokens remain in this browser; requests never enumerate other learners' sessions.
window.StudyLibrary = (() => {
    const KEY = 'study-coach-library:v1';
    const activeKeys = {practice: 'study-coach-session:v1', exam: 'study-coach-exam:v1'};
    let available = true;
    function valid(entry) {
        return entry && ['practice', 'exam'].includes(entry.kind)
            && typeof entry.token === 'string' && entry.token.length > 0 && entry.token.length <= 100;
    }
    function list() {
        let entries = [];
        try {
            try { entries = JSON.parse(localStorage.getItem(KEY) || '[]'); } catch { entries = []; }
            if (!Array.isArray(entries)) entries = [];
            entries = entries.filter(valid).map(({kind, token}) => ({kind, token}));
            for (const [kind, key] of Object.entries(activeKeys)) {
                const token = localStorage.getItem(key);
                if (valid({kind, token}) && !entries.some(entry => entry.kind === kind && entry.token === token)) entries.push({kind, token});
            }
        } catch { available = false; }
        return entries.filter((entry, index, all) => all.findIndex(other => other.kind === entry.kind && other.token === entry.token) === index).slice(-50);
    }
    function remember(kind, token) {
        if (!valid({kind, token})) return;
        const entries = list().filter(entry => entry.kind !== kind || entry.token !== token);
        entries.push({kind, token});
        try { localStorage.setItem(KEY, JSON.stringify(entries.slice(-50))); }
        catch { available = false; }
    }
    function saveActive(kind, token) {
        if (!valid({kind, token})) throw new Error('Invalid saved session reference.');
        try {
            localStorage.setItem(activeKeys[kind], token);
            return true;
        } catch {
            available = false;
            return false;
        }
    }
    function resume(entry) {
        if (!entry || !Object.hasOwn(activeKeys, entry.kind)) throw new Error('Invalid saved session reference.');
        const path = entry.kind === 'exam' ? '/exam?resume=1' : '/?resume=1';
        if (Object.hasOwn(entry, 'id')) {
            if (!/^[a-f0-9]{64}$/.test(entry.id)) throw new Error('Invalid account session reference.');
            window.location.assign(path + '#account=' + entry.id);
        } else {
            if (!saveActive(entry.kind, entry.token)) throw new Error('Enable browser storage to open this browser-only session.');
            remember(entry.kind, entry.token);
            window.location.assign(path);
        }
    }
    async function openAccount(kind, id) {
        const response = await fetch('/account/open', {
            method: 'POST', headers: {'Content-Type': 'application/json', 'X-Study-Coach': '1'},
            body: JSON.stringify({id}), signal: AbortSignal.timeout(15000),
        });
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Sign in again to open this session.');
        if (data.kind !== kind || !valid({kind, token: data.session_token})) {
            throw new Error('Open this session from its card on your dashboard.');
        }
        return data.session_token;
    }
    async function accountResumeToken(kind) {
        const match = /^#account=([a-f0-9]{64})$/.exec(window.location.hash);
        if (!match) throw new Error('Reopen the saved session from your dashboard.');
        const token = await openAccount(kind, match[1]);
        if (saveActive(kind, token)) remember(kind, token);
        return token;
    }
    for (const entry of list()) remember(entry.kind, entry.token);
    return {list, remember, resume, accountResumeToken, saveActive, storageAvailable: () => available};
})();
