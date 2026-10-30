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
    function resume(entry) {
        if (!valid(entry)) throw new Error('Invalid saved session reference.');
        localStorage.setItem(activeKeys[entry.kind], entry.token);
        remember(entry.kind, entry.token);
        window.location.assign(entry.kind === 'exam' ? '/exam?resume=1' : '/?resume=1');
    }
    for (const entry of list()) remember(entry.kind, entry.token);
    return {list, remember, resume, storageAvailable: () => available};
})();
