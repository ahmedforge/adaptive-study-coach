const $ = id => document.getElementById(id);
const TOKEN_KEY = 'study-coach-exam:v1';
let token = '';
let storageWorks = true;
let exam = null;
let questionIndex = 0;
let working = false;
let localDeadline = 0;
let timer = null;
let nextExpiryCheck = 0;
try { token = localStorage.getItem(TOKEN_KEY) || ''; } catch { storageWorks = false; }
function node(tag, text) {
    const result = document.createElement(tag);
    result.textContent = text;
    return result;
}
function topicLabel(topic) { return topic.replaceAll('_', ' '); }
function status(text) { $('exam-status').textContent = text; }
function busy(value) {
    working = value;
    document.querySelectorAll('button, input, select').forEach(control => { control.disabled = value; });
    if (!value && exam?.status === 'active') {
        $('previous-question').disabled = questionIndex === 0;
        $('next-question').disabled = questionIndex === exam.questions.length - 1;
        if (Date.now() >= localDeadline) {
            $('exam-question').querySelectorAll('button, input').forEach(control => { control.disabled = true; });
        }
    }
}
async function request(path, method = 'GET', body) {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    let response;
    try {
        response = await fetch(path, {method, signal: controller.signal,
            headers: {'Content-Type': 'application/json', ...(token ? {Authorization: `Bearer ${token}`} : {})},
            ...(body === undefined ? {} : {body: JSON.stringify(body)})});
    } catch {
        throw new Error('Connection interrupted. Resume to check which answers were saved.');
    } finally { clearTimeout(timeout); }
    let data;
    try { data = await response.json(); } catch { throw new Error('Unexpected response. Resume to check saved answers.'); }
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Could not save. Resume to check saved answers.');
    return data;
}
function savedMessage() {
    return storageWorks ? 'Saved on this server. Resume from this browser if you leave.'
        : 'Saved on this server, but browser storage is blocked. Keep this tab open to retain access.';
}
function applyExam(data) {
    exam = data;
    localDeadline = Date.now() + Math.max(0, Date.parse(data.expires_at) - Date.parse(data.server_now));
    $('exam-setup').hidden = true;
    $('resume-exam').hidden = false;
    $('new-exam').hidden = false;
    $('submit-confirmation').hidden = true;
    $('exam-workspace').hidden = data.status !== 'active';
    $('exam-report').hidden = data.status !== 'completed';
    if (timer) clearInterval(timer);
    if (data.status === 'completed') renderReport();
    else {
        questionIndex = Math.min(questionIndex, data.questions.length - 1);
        renderQuestion();
        timer = setInterval(updateTimer, 1000);
        updateTimer();
    }
}
async function resume() {
    if (working) return;
    busy(true); status('Loading saved exam…');
    try { applyExam(await request('/exams/current')); status(savedMessage()); }
    catch (error) { nextExpiryCheck = Date.now() + 5000; status(error.message); }
    finally { busy(false); }
}
function updateTimer() {
    if (!exam || exam.status !== 'active') return;
    const seconds = Math.max(0, Math.ceil((localDeadline - Date.now()) / 1000));
    $('exam-clock').textContent = `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')} remaining`;
    if (seconds === 0 && !working && Date.now() >= nextExpiryCheck) {
        // The server decides expiry; a browser clock change cannot extend the exam.
        resume();
    }
}
function renderQuestion(focus = false) {
    const q = exam.questions[questionIndex];
    const answered = Object.keys(exam.answers).length;
    $('exam-progress').textContent = `${answered} / ${exam.questions.length} answered. Green buttons mark saved answers.`;
    $('question-nav').replaceChildren();
    exam.questions.forEach((question, index) => {
        const button = node('button', String(index + 1));
        button.type = 'button';
        button.setAttribute('aria-label', `Question ${index + 1}, ${exam.answers[question.id] ? 'answered' : 'unanswered'}`);
        if (exam.answers[question.id]) button.className = 'answered';
        if (index === questionIndex) button.setAttribute('aria-current', 'step');
        button.addEventListener('click', () => { questionIndex = index; renderQuestion(true); });
        $('question-nav').append(button);
    });
    const box = $('exam-question');
    box.replaceChildren();
    const heading = node('h2', `Question ${questionIndex + 1} of ${exam.questions.length}`);
    heading.id = 'current-question-heading'; heading.tabIndex = -1;
    box.append(heading, node('p', topicLabel(q.topic)));
    const fieldset = document.createElement('fieldset');
    fieldset.append(node('legend', q.question));
    for (const option of q.options) {
        const label = document.createElement('label');
        const input = document.createElement('input');
        input.type = 'radio'; input.name = 'exam-answer'; input.value = option;
        input.checked = exam.answers[q.id] === option;
        input.addEventListener('change', () => saveAnswer(q.id, option));
        label.append(input, document.createTextNode(option));
        fieldset.append(label);
    }
    const clear = node('button', 'Clear answer'); clear.type = 'button';
    clear.addEventListener('click', () => saveAnswer(q.id, null));
    box.append(fieldset, clear);
    $('submit-confirmation').hidden = true;
    busy(working);
    if (focus) heading.focus();
}
async function saveAnswer(questionId, selected) {
    if (working) return;
    busy(true); status('Saving answer…');
    let saved = false;
    try {
        applyExam(await request('/exams/current/answers', 'PUT', {
            question_id: questionId, selected_answer: selected, version: exam.version}));
        status(savedMessage());
        saved = true;
    } catch (error) {
        renderQuestion();
        status(error.message);
    } finally {
        busy(false);
        if (saved && exam.status === 'active') {
            const selectedInput = [...$('exam-question').querySelectorAll('input')].find(input => input.value === selected);
            (selectedInput || $('current-question-heading')).focus();
        }
    }
}
function renderReport() {
    const box = $('exam-report'); box.replaceChildren(); box.className = 'card';
    const heading = node('h2', 'Your exam report'); heading.tabIndex = -1;
    box.append(heading, node('p', exam.completion_reason === 'time_expired'
        ? 'Time expired. Your saved answers have been graded.' : 'Exam submitted. Your saved answers have been graded.'));
    const score = node('p', `${exam.summary.correct} / ${exam.summary.total} · ${exam.score_percent}%`); score.className = 'score';
    box.append(score, node('p', `${exam.summary.incorrect} incorrect · ${exam.summary.unanswered} unanswered. One mark per correct answer; no negative marking.`));
    const wrap = document.createElement('div'); wrap.className = 'table-wrap';
    const table = document.createElement('table'); table.append(node('caption', 'Topic breakdown'));
    const head = document.createElement('thead'); const row = document.createElement('tr');
    for (const title of ['Topic', 'Correct', 'Incorrect', 'Unanswered']) {
        const cell = node('th', title); cell.scope = 'col'; row.append(cell);
    }
    head.append(row); const body = document.createElement('tbody');
    for (const topic of exam.summary.topics) {
        const tr = document.createElement('tr'); const th = node('th', topicLabel(topic.topic)); th.scope = 'row'; tr.append(th);
        for (const key of ['correct', 'incorrect', 'unanswered']) tr.append(node('td', topic[key]));
        body.append(tr);
    }
    table.append(head, body); wrap.append(table); box.append(wrap, node('h3', 'Review questions and solutions'));
    for (const [index, result] of exam.results.entries()) {
        const entry = document.createElement('details');
        entry.append(node('summary', `${index + 1}. ${topicLabel(result.topic)} · ${result.is_correct ? 'Correct' : result.selected_answer === null ? 'Unanswered' : 'Incorrect'}`));
        entry.append(node('p', result.question), node('p', `Your answer: ${result.selected_answer ?? 'Unanswered'}`),
            node('p', `Correct answer: ${result.correct_answer}`), node('p', result.explanation));
        box.append(entry);
    }
    box.append(node('p', 'Use missed topics to guide your next study session. This score describes this question sample, not long-term mastery.'));
    heading.focus();
}
$('exam-setup').addEventListener('submit', async event => {
    event.preventDefault(); if (working) return;
    busy(true); status('Preparing and saving your exam…');
    try {
        const data = await request('/exams', 'POST', {question_count: Number($('exam-size').value), duration_minutes: Number($('exam-duration').value)});
        token = data.exam_token;
        try { localStorage.setItem(TOKEN_KEY, token); } catch { storageWorks = false; }
        questionIndex = 0; applyExam(data); status(savedMessage());
        $('current-question-heading').focus();
    } catch (error) { status(error.message); }
    finally { busy(false); }
});
$('resume-exam').addEventListener('click', resume);
$('new-exam').addEventListener('click', () => {
    if (timer) clearInterval(timer);
    exam = null;
    $('exam-workspace').hidden = true; $('exam-report').hidden = true; $('exam-setup').hidden = false;
    status('Set up another exam. Starting it replaces this browser’s exam resume link; an unfinished exam’s timer keeps running on the server.');
});
$('previous-question').addEventListener('click', () => { if (questionIndex > 0) { questionIndex--; renderQuestion(true); } });
$('next-question').addEventListener('click', () => { if (questionIndex < exam.questions.length - 1) { questionIndex++; renderQuestion(true); } });
$('review-submit').addEventListener('click', () => {
    const answered = Object.keys(exam.answers).length;
    $('submission-summary').textContent = `${answered} answered; ${exam.questions.length - answered} unanswered.`;
    $('submit-confirmation').hidden = false; $('confirm-submit').focus();
});
$('cancel-submit').addEventListener('click', () => { $('submit-confirmation').hidden = true; $('review-submit').focus(); });
$('confirm-submit').addEventListener('click', async () => {
    if (working) return;
    busy(true); status('Submitting saved answers…');
    try { applyExam(await request('/exams/current/submit', 'POST')); status('Exam complete. Report saved.'); }
    catch (error) { status(error.message); }
    finally { busy(false); }
});
if (token) { $('exam-setup').hidden = true; $('resume-exam').hidden = false; $('new-exam').hidden = false; status('A saved exam is available. Resume it to continue or view its report.'); }
else status('Ready to start.');
