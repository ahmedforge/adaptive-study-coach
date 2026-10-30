const form = document.getElementById('diagnostic-form');
const questionsBox = document.getElementById('diagnostic-questions');
const reportBox = document.getElementById('report');
const practiceBox = document.getElementById('practice');
const statusBox = document.getElementById('save-status');
const resumeControls = document.getElementById('resume-controls');
const resumeButton = document.getElementById('resume-session');
const newButton = document.getElementById('new-session');
const STORAGE_KEY = 'study-coach-session:v1';
let diagnosticQuestions = [];
let sessionToken = '';
let browserStorageWorks = true;
let activeQuestion = null;
try { sessionToken = localStorage.getItem(STORAGE_KEY) || ''; }
catch { browserStorageWorks = false; }

function element(tag, text) {
    const node = document.createElement(tag);
    node.textContent = text;
    return node;
}
function busy(value) {
    document.querySelectorAll('button, input, select').forEach(node => { node.disabled = value; });
}
function showDiagnostic(value) {
    form.hidden = !value;
    document.getElementById('diagnostic-heading').hidden = !value;
    document.getElementById('diagnostic-help').hidden = !value;
}
async function request(path, options = {}) {
    const response = await fetch(path, options);
    let data;
    try { data = await response.json(); }
    catch { throw new Error('Unexpected response. Please retry.'); }
    if (!response.ok) {
        throw new Error(typeof data.detail === 'string' ? data.detail : 'Request failed. Please retry.');
    }
    return data;
}
function headers() {
    return { 'Content-Type': 'application/json', Authorization: `Bearer ${sessionToken}` };
}
function savedStatus() {
    statusBox.textContent = browserStorageWorks
        ? 'Progress saved. Resume from this browser after closing or restarting the app.'
        : 'Progress saved on this server, but browser storage is unavailable. Keep this tab open to retain access.';
}
function topicLabel(topic) {
    return topic.replaceAll('_', ' ');
}
function renderDiagnosticSummary(summary, source = 'diagnostic') {
    const details = document.createElement('details');
    details.append(element('summary', `${source === 'mock_exam' ? 'Mock exam' : 'Diagnostic'}: ${summary.correct} / ${summary.total} correct, ${summary.incorrect} incorrect, ${summary.unanswered} unanswered`));
    details.append(element('p', 'Practice includes topics with incorrect or unanswered questions, ordered by the number missed. These results are a starting point, not a mastery assessment.'));
    const table = document.createElement('table');
    table.append(element('caption', source === 'mock_exam' ? 'Results from your saved mock exam' : 'Results from your saved diagnostic'));
    const head = document.createElement('thead');
    const headings = document.createElement('tr');
    for (const title of ['Topic', 'Correct', 'Incorrect', 'Unanswered']) {
        const cell = element('th', title);
        cell.scope = 'col';
        headings.append(cell);
    }
    head.append(headings);
    const body = document.createElement('tbody');
    for (const topic of summary.topics) {
        const row = document.createElement('tr');
        const label = element('th', topicLabel(topic.topic));
        label.scope = 'row';
        row.append(label);
        for (const key of ['correct', 'incorrect', 'unanswered']) row.append(element('td', topic[key]));
        body.append(row);
    }
    table.append(head, body);
    details.append(table);
    reportBox.append(details);
}
function renderPracticeHistory(history) {
    const details = document.createElement('details');
    details.append(element('summary', `Practice history (${history.length} answers)`));
    details.append(element('p', 'Review saved answers and explanations, newest first.'));
    const topicLabelNode = element('label', 'Filter by topic ');
    const topicFilter = document.createElement('select');
    topicFilter.setAttribute('aria-label', 'Filter history by topic');
    const allTopics = element('option', 'All topics');
    allTopics.value = '';
    topicFilter.append(allTopics);
    for (const topic of [...new Set(history.map(attempt => attempt.topic))]) {
        const option = element('option', topicLabel(topic));
        option.value = topic;
        topicFilter.append(option);
    }
    topicLabelNode.append(topicFilter);
    const mistakesLabel = document.createElement('label');
    const mistakesOnly = document.createElement('input');
    mistakesOnly.type = 'checkbox';
    mistakesLabel.append(mistakesOnly, document.createTextNode(' Show incorrect answers only'));
    const count = element('p', '');
    count.setAttribute('role', 'status');
    const list = document.createElement('div');
    const more = element('button', 'Show more answers');
    more.type = 'button';
    let limit = 10;
    function updateHistory() {
        const matches = history.map((attempt, index) => ({attempt, number: index + 1}))
            .reverse().filter(({attempt}) => (!topicFilter.value || attempt.topic === topicFilter.value)
                && (!mistakesOnly.checked || !attempt.is_correct));
        list.replaceChildren();
        count.textContent = matches.length
            ? `Showing ${Math.min(limit, matches.length)} of ${matches.length} matching answers.`
            : 'No saved answers match these filters.';
        for (const {attempt, number} of matches.slice(0, limit)) {
            const entry = document.createElement('details');
            entry.className = 'history-entry';
            entry.append(element('summary', `Answer ${number}: ${topicLabel(attempt.topic)} — ${attempt.is_correct ? 'Correct' : 'Incorrect'}`));
            entry.append(element('p', attempt.question));
            entry.append(element('p', `Your answer: ${attempt.selected_answer}`));
            entry.append(element('p', `Correct answer: ${attempt.correct_answer}`));
            entry.append(element('p', attempt.explanation));
            list.append(entry);
        }
        more.hidden = matches.length <= limit;
    }
    topicFilter.addEventListener('change', () => { limit = 10; updateHistory(); });
    mistakesOnly.addEventListener('change', () => { limit = 10; updateHistory(); });
    more.addEventListener('click', () => {
        const firstNew = limit;
        limit += 10;
        updateHistory();
        list.children[firstNew]?.querySelector('summary').focus();
    });
    details.append(topicLabelNode, mistakesLabel, count, list, more);
    updateHistory();
    reportBox.append(details);
}
function renderSession(data, reviewAnswer = true) {
    window.StudyLibrary?.remember('practice', sessionToken);
    activeQuestion = null;
    showDiagnostic(false);
    resumeControls.hidden = false;
    resumeButton.textContent = 'Resume latest saved progress';
    reportBox.replaceChildren(element('h2', data.state.status === 'complete' ? 'Practice cycle complete' : 'Saved progress'));
    renderDiagnosticSummary(data.diagnostic_summary, data.assessment_source);
    const correct = data.history.filter(attempt => attempt.is_correct).length;
    reportBox.append(element('p', `${data.history.length} practice answers saved; ${correct} correct.`));
    reportBox.append(element('p', `Remaining topics: ${data.state.weak_topics.map(topicLabel).join(', ') || 'None in this cycle'}`));
    if (data.state.current_topic) {
        reportBox.append(element('p', `Current focus: ${topicLabel(data.state.current_topic)}`));
        reportBox.append(element('p', `Topic progress: ${data.state.correct_streak} / ${data.state.target_correct} consecutive correct answers.`));
        reportBox.append(element('p', 'A wrong answer resets this streak. Reaching the target moves you to the next topic; it does not measure long-term mastery.'));
    }
    if (data.history.length) {
        const latest = data.history[data.history.length - 1];
        const feedbackHeading = element('h3', 'Last answer');
        feedbackHeading.id = 'answer-review-heading';
        feedbackHeading.tabIndex = -1;
        reportBox.append(feedbackHeading);
        reportBox.append(element('p', latest.question));
        reportBox.append(element('p', `${latest.is_correct ? 'Correct' : 'Incorrect'}. Your answer: ${latest.selected_answer}. Correct answer: ${latest.correct_answer}.`));
        reportBox.append(element('p', latest.explanation));
        renderPracticeHistory(data.history);
    }
    practiceBox.replaceChildren();
    if (!data.practice_question) {
        practiceBox.append(element('p', 'This practice cycle is complete. Start a new diagnostic when you are ready.'));
        return;
    }
    if (reviewAnswer && data.history.length) {
        practiceBox.append(element('h2', 'Review before continuing'));
        practiceBox.append(element('p', 'Your answer and explanation are saved above. Take a moment to review them before the next question.'));
        const next = element('button', 'Continue practice');
        next.type = 'button';
        next.addEventListener('click', () => {
            renderSession(data, false);
            document.getElementById('practice-heading').focus();
        });
        practiceBox.append(next);
        return;
    }
    activeQuestion = data.practice_question;
    const practiceHeading = element('h2', 'Targeted Practice');
    practiceHeading.id = 'practice-heading';
    practiceHeading.tabIndex = -1;
    practiceBox.append(practiceHeading);
    practiceBox.append(element('p', activeQuestion.generation_source === 'seed_fallback'
        ? 'Question bank practice - AI generation unavailable or rejected.' : 'AI-generated practice'));
    practiceBox.append(element('p', activeQuestion.question));
    for (const option of activeQuestion.options) {
        const label = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'radio'; input.name = 'practice_answer'; input.value = option;
        label.append(input, document.createTextNode(` ${option}`));
        practiceBox.append(label);
    }
    const submit = element('button', 'Submit Practice Answer');
    submit.type = 'button';
    submit.addEventListener('click', submitPracticeAnswer);
    practiceBox.append(submit);
}
async function loadDiagnostic() {
    const data = await request('/diagnostic/questions');
    diagnosticQuestions = data.questions;
    questionsBox.replaceChildren();
    diagnosticQuestions.forEach((question, index) => {
        const box = document.createElement('div');
        box.append(element('p', `${index + 1}. ${question.question}`));
        for (const option of question.options) {
            const label = document.createElement('label');
            const input = document.createElement('input');
            input.type = 'radio'; input.name = question.id; input.value = option;
            label.append(input, document.createTextNode(` ${option}`));
            box.append(label);
        }
        questionsBox.append(box);
    });
}
form.addEventListener('submit', async event => {
    event.preventDefault();
    const fields = new FormData(form);
    busy(true); statusBox.textContent = 'Saving diagnostic and preparing practice...';
    try {
        const answers = diagnosticQuestions.map(q => ({ question_id: q.id, selected_answer: fields.get(q.id) }));
        const data = await request('/sessions', {
            method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ answers }),
        });
        sessionToken = data.session_token;
        try { localStorage.setItem(STORAGE_KEY, sessionToken); }
        catch { browserStorageWorks = false; }
        renderSession(data); savedStatus();
    } catch (error) { statusBox.textContent = error.message; }
    finally { busy(false); }
});
async function submitPracticeAnswer() {
    if (!activeQuestion) return;
    const selected = document.querySelector('input[name="practice_answer"]:checked');
    if (!selected) { statusBox.textContent = 'Please select an answer.'; return; }
    const body = { question_id: activeQuestion.id, selected_answer: selected.value };
    busy(true); statusBox.textContent = 'Saving answer and preparing the next question...';
    try {
        const data = await request('/sessions/current/answers', {
            method: 'POST', headers: headers(), body: JSON.stringify(body),
        });
        renderSession(data); savedStatus();
        document.getElementById('answer-review-heading').focus();
    } catch (error) { statusBox.textContent = error.message; }
    finally { busy(false); }
}
resumeButton.addEventListener('click', async () => {
    busy(true); statusBox.textContent = 'Loading saved progress...';
    try { renderSession(await request('/sessions/current', { headers: headers() })); savedStatus(); }
    catch (error) { statusBox.textContent = error.message; }
    finally { busy(false); }
});
newButton.addEventListener('click', () => {
    sessionToken = ''; activeQuestion = null;
    try { localStorage.removeItem(STORAGE_KEY); } catch { browserStorageWorks = false; }
    reportBox.replaceChildren(); practiceBox.replaceChildren();
    resumeControls.hidden = true; form.reset(); showDiagnostic(true);
    statusBox.textContent = 'Ready for a new diagnostic.';
});
async function initialize() {
    busy(true);
    try {
        await loadDiagnostic();
        if (sessionToken) {
            resumeControls.hidden = false;
            statusBox.textContent = 'Saved practice is available. Resume it or start a new diagnostic.';
            showDiagnostic(false);
            if (new URLSearchParams(window.location.search).get('resume') === '1') {
                renderSession(await request('/sessions/current', { headers: headers() }));
                savedStatus();
            }
        }
    } catch (error) { statusBox.textContent = error.message; }
    finally { busy(false); }
}
initialize();
