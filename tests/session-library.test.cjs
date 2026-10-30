const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '../app/static/session-library.js'), 'utf8');
const KEY = 'study-coach-library:v1';
function load(initial = {}, blocked = false) {
    const values = new Map(Object.entries(initial));
    let destination;
    const localStorage = {
        getItem(key) { if (blocked) throw new Error('blocked'); return values.get(key) ?? null; },
        setItem(key, value) { if (blocked) throw new Error('blocked'); values.set(key, value); },
    };
    const window = {location: {assign(url) { destination = url; }}};
    vm.runInNewContext(source, {window, localStorage});
    return {library: window.StudyLibrary, values, destination: () => destination};
}
const plain = value => JSON.parse(JSON.stringify(value));

test('migrates existing practice and exam links without losing either', () => {
    const {library, values} = load({'study-coach-session:v1': 'practice-secret', 'study-coach-exam:v1': 'exam-secret'});
    assert.deepEqual(plain(library.list()), [{kind:'practice', token:'practice-secret'}, {kind:'exam', token:'exam-secret'}]);
    assert.equal(JSON.parse(values.get(KEY)).length, 2);
});
test('preserves older sessions across new sessions and reloads', () => {
    const state = load();
    state.library.remember('practice', 'first');
    state.library.remember('practice', 'second');
    state.library.remember('practice', 'first');
    const reloaded = load(Object.fromEntries(state.values));
    assert.deepEqual(plain(reloaded.library.list()), [{kind:'practice', token:'second'}, {kind:'practice', token:'first'}]);
});
test('bounds retained links and keeps newest fifty', () => {
    const {library} = load();
    for (let i = 0; i < 55; i++) library.remember('exam', `secret-${i}`);
    assert.equal(library.list().length, 50);
    assert.equal(library.list()[0].token, 'secret-5');
    assert.equal(library.list()[49].token, 'secret-54');
});
test('invalid stored records cannot become resume destinations', () => {
    const {library} = load({[KEY]: JSON.stringify([{kind:'account', token:'x'}, {kind:'exam', token:''}, {kind:'exam', token:5}, {kind:'practice', token:'valid', url:'https://invalid.example'}])});
    assert.deepEqual(plain(library.list()), [{kind:'practice', token:'valid'}]);
    assert.throws(() => library.resume({kind:'account', token:'x'}));
});
test('corrupt JSON recovers current valid links', () => {
    const {library} = load({[KEY]:'{broken', 'study-coach-session:v1':'saved'});
    assert.equal(library.list()[0].token, 'saved');
});
test('blocked storage is reported and does not crash remembering', () => {
    const {library} = load({}, true);
    library.remember('practice', 'saved');
    assert.equal(library.storageAvailable(), false);
    assert.equal(library.list().length, 0);
});
test('resuming selects the requested token and keeps secrets out of URLs', () => {
    const state = load();
    state.library.resume({kind:'exam', token:'exam-private-token'});
    assert.equal(state.values.get('study-coach-exam:v1'), 'exam-private-token');
    assert.equal(state.destination(), '/exam?resume=1');
    state.library.resume({kind:'practice', token:'practice-private-token'});
    assert.equal(state.values.get('study-coach-session:v1'), 'practice-private-token');
    assert.equal(state.destination(), '/?resume=1');
    assert.equal(state.library.list().length, 2);
});
