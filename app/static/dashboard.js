const el = id => document.getElementById(id);
let references = [], progress = null, limit = 10, accountOffset = 0, loadedUsername = null;
function node(tag, text) { const result = document.createElement(tag); result.textContent = text; return result; }
function label(topic) { return topic.replaceAll('_', ' '); }
function metric(title, value) {
    const box = document.createElement('div'); box.className = 'metric';
    box.append(node('strong', value), node('span', title)); el('progress-overview').append(box);
}
function renderSessions() {
    const kind = el('session-filter').value;
    const matches = progress.sessions.filter(session => kind === 'all' || session.kind === kind);
    const box = el('saved-sessions'); box.replaceChildren();
    if (!matches.length) box.append(node('p', 'No saved sessions match this view. Start practice or a mock exam to build your history.'));
    for (const session of matches.slice(0, limit)) {
        const card = document.createElement('article'); card.className = 'session';
        const isExam = session.kind === 'exam';
        card.append(node('h3', isExam ? 'Mock exam' : session.assessment_source === 'mock_exam' ? 'Exam revision practice' : 'Diagnostic practice'));
        const timestamp = new Date(session.timestamp);
        card.append(node('p', `${session.timestamp_label}: ${Number.isNaN(timestamp.getTime()) ? 'Unavailable' : timestamp.toLocaleString()}`));
        if (isExam) {
            card.append(node('p', session.status === 'completed'
                ? `Completed · ${session.correct} / ${session.question_count} correct (${session.score_percent}%)`
                : `${session.status === 'time_elapsed' ? 'Time elapsed — open to grade saved answers' : 'In progress'} · ${session.answered} / ${session.question_count} answered`));
        } else {
            card.append(node('p', `${session.answers} practice answers · ${session.correct} correct · ${session.status === 'complete' ? 'Cycle complete' : `${session.remaining_topics.length} topics remaining`}`));
            if (session.current_topic) card.append(node('p', `Current focus: ${label(session.current_topic)} · streak ${session.correct_streak} / ${session.target_correct}`));
        }
        const open = node('button', isExam ? session.status === 'active' ? 'Continue exam' : 'Open exam report' : 'Open saved practice');
        open.type = 'button';
        const reference = references[session.index];
        open.addEventListener('click', async () => {
            try {
                let resumeReference = reference;
                if (reference.id) {
                    open.disabled = true;
                    const response = await fetch('/account/open', {method:'POST', headers:{'Content-Type':'application/json', 'X-Study-Coach':'1'}, body:JSON.stringify({id:reference.id}), signal:AbortSignal.timeout(15000)});
                    const data = await response.json();
                    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Sign in again to open this session.');
                    resumeReference = {kind:data.kind, token:data.session_token};
                }
                window.StudyLibrary.resume(resumeReference);
            }
            catch (error) { el('progress-status').textContent = error.message || 'Enable browser storage to open this session.'; }
            finally { open.disabled = false; }
        });
        card.append(open); box.append(card);
    }
    el('more-sessions').hidden = matches.length <= limit;
}
function renderProgress() {
    el('progress-overview').replaceChildren();
    metric('Practice sessions', progress.totals.practice_sessions);
    metric('Practice answers', progress.totals.practice_answers);
    metric('Correct practice answers', progress.totals.practice_correct);
    metric('Completed mock exams', `${progress.totals.completed_exams} / ${progress.totals.exams}`);
    const revisit = el('revisit'); revisit.replaceChildren(); revisit.hidden = !progress.revisit.length;
    if (progress.revisit.length) {
        revisit.append(node('h2', 'Topics to revisit'), node('p', 'Most missed or unanswered questions across your completed exams in this view. Open an exam report to start targeted revision.'));
        const list = document.createElement('ul');
        for (const topic of progress.revisit) list.append(node('li', `${label(topic.topic)}: ${topic.missed} missed or unanswered`));
        revisit.append(list);
    }
    const topicBox = el('topic-progress'); topicBox.replaceChildren(); topicBox.hidden = !progress.topics.length;
    if (progress.topics.length) {
        topicBox.append(node('h2', 'Topic results'));
        const wrap = document.createElement('div'); wrap.className = 'table-wrap';
        const table = document.createElement('table'); table.append(node('caption', 'Correct answers / total attempts or assessed questions'));
        const head = document.createElement('thead'), row = document.createElement('tr');
        for (const text of ['Topic', 'Practice', 'Completed exams']) { const th = node('th', text); th.scope = 'col'; row.append(th); }
        head.append(row); const body = document.createElement('tbody');
        for (const topic of progress.topics) {
            const tr = document.createElement('tr'), th = node('th', label(topic.topic)); th.scope = 'row'; tr.append(th);
            tr.append(node('td', topic.practice_total ? `${topic.practice_correct} / ${topic.practice_total}` : 'No attempts'),
                node('td', topic.exam_total ? `${topic.exam_correct} / ${topic.exam_total}` : 'No results'));
            body.append(tr);
        }
        table.append(head, body); wrap.append(table); topicBox.append(wrap);
    }
    limit = 10; renderSessions();
}
async function refresh() {
    el('refresh-progress').disabled = true; el('session-filter').disabled = true;
    el('more-sessions').disabled = true;
    el('newer-account-sessions').disabled = true; el('older-account-sessions').disabled = true;
    el('progress-status').textContent = 'Loading saved progress…';
    try {
        const whoResponse = await fetch('/account/me', {signal: AbortSignal.timeout(15000)});
        if (!whoResponse.ok) throw new Error('Could not check sign-in status. Please refresh.');
        const user = await whoResponse.json();
        const username = user.authenticated ? user.username : null;
        if (username !== loadedUsername) {
            el('progress-overview').replaceChildren(); el('saved-sessions').replaceChildren();
            el('revisit').hidden = true; el('topic-progress').hidden = true;
            el('more-sessions').hidden = true; progress = null; references = []; accountOffset = 0;
        }
        let requested, hasMore = false;
        if (user.authenticated) {
            const libraryResponse = await fetch(`/account/library?offset=${accountOffset}`, {signal: AbortSignal.timeout(15000)});
            const library = await libraryResponse.json();
            if (!libraryResponse.ok) throw new Error(library.detail || 'Account progress is unavailable.');
            requested = library.sessions; hasMore = library.has_more;
            el('progress-context').textContent = `Signed in as ${user.username}. Results below cover this page of account sessions.`;
            el('progress-storage-help').textContent = 'Account progress is stored on this server and available after signing in on another device. Use the older/newer controls to browse your history. Totals and topic results apply to the current page of up to 50 sessions. Browser-only progress can be imported from Your account.';
        } else {
            accountOffset = 0; requested = window.StudyLibrary.list();
            el('progress-context').textContent = 'Progress from session links saved in this browser. Sign in for account history across devices.';
            el('progress-storage-help').textContent = 'Anonymous progress uses up to 50 session links retained in this browser. Clearing storage loses those links. Account-owned links require the owner to sign in; account history is stored on this server.';
        }
        const response = await fetch('/progress/summary', {method: 'POST',
            headers: {'Content-Type': 'application/json', 'X-Study-Coach':'1'}, body: JSON.stringify({sessions: requested}),
            signal: AbortSignal.timeout(15000)});
        const data = await response.json();
        if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Progress could not be loaded.');
        references = requested; progress = data; loadedUsername = username; renderProgress();
        el('newer-account-sessions').hidden = !user.authenticated || accountOffset === 0;
        el('older-account-sessions').hidden = !user.authenticated || !hasMore;
        el('progress-status').textContent = !user.authenticated && !window.StudyLibrary.storageAvailable()
            ? 'Browser storage is blocked; saved session links are unavailable.'
            : `${progress.sessions.length} ${user.authenticated ? 'account' : 'saved'} sessions loaded.${data.unavailable.length ? ` ${data.unavailable.length} links are unavailable on this server.` : ''}`;
    } catch (error) { el('progress-status').textContent = error.name === 'TimeoutError' ? 'Loading timed out. Please refresh.' : error.message; }
    finally {
        el('refresh-progress').disabled = false; el('session-filter').disabled = false; el('more-sessions').disabled = false;
        el('newer-account-sessions').disabled = false; el('older-account-sessions').disabled = false;
    }
}
el('refresh-progress').addEventListener('click', refresh);
el('newer-account-sessions').addEventListener('click', () => { accountOffset = Math.max(0, accountOffset - 50); refresh(); });
el('older-account-sessions').addEventListener('click', () => { accountOffset += 50; refresh(); });
el('session-filter').addEventListener('change', () => { if (progress) { limit = 10; renderSessions(); } });
el('more-sessions').addEventListener('click', () => {
    const firstNew = limit; limit += 10; renderSessions();
    el('saved-sessions').children[firstNew]?.querySelector('button')?.focus();
});
refresh();
