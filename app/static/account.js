const $account = id => document.getElementById(id);
function accountBusy(value) { document.querySelectorAll('button, input').forEach(control => { control.disabled = value; }); }
function accountStatus(text) { $account('account-status').textContent = text; }
async function accountRequest(path, method = 'GET', body) {
    const response = await fetch(path, {method, headers: {'Content-Type':'application/json', 'X-Study-Coach':'1'},
        ...(body === undefined ? {} : {body: JSON.stringify(body)}), signal: AbortSignal.timeout(15000)});
    const data = await response.json();
    if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'The account request could not be completed.');
    return data;
}
function showAccount(user) {
    $account('guest-account').hidden = user.authenticated;
    $account('signed-in-account').hidden = !user.authenticated;
    if (user.authenticated) $account('signed-in-heading').textContent = `Signed in as ${user.username}`;
    document.querySelectorAll('input[type="password"]').forEach(input => { input.value = ''; });
}
async function accountAction(action) {
    accountBusy(true);
    try { await action(); }
    catch (error) { accountStatus(error.name === 'TimeoutError' ? 'The request timed out. Reload to check your sign-in status before retrying.' : error.message); }
    finally { accountBusy(false); }
}
$account('login-form').addEventListener('submit', event => {
    event.preventDefault();
    accountAction(async () => {
        const user = await accountRequest('/account/login', 'POST', {username:$account('login-username').value, password:$account('login-password').value});
        showAccount(user); accountStatus('Signed in. Open your dashboard to resume saved progress.');
    });
});
$account('register-form').addEventListener('submit', event => {
    event.preventDefault();
    if ($account('register-password').value !== $account('register-confirm').value) { accountStatus('The passwords do not match.'); return; }
    accountAction(async () => {
        const user = await accountRequest('/account/register', 'POST', {username:$account('register-username').value, password:$account('register-password').value});
        showAccount(user); accountStatus('Account created. New sessions belong to your account; import existing browser progress below if you want to keep it here.');
    });
});
for (const [id, path] of [['logout','/account/logout'], ['logout-all','/account/logout-all']]) {
    $account(id).addEventListener('click', () => accountAction(async () => {
        showAccount(await accountRequest(path, 'POST'));
        accountStatus(id === 'logout-all' ? 'Signed out of all browsers.' : 'Signed out. Your account progress remains saved.');
    }));
}
$account('import-progress').addEventListener('click', () => accountAction(async () => {
    const data = await accountRequest('/account/claim', 'POST', {sessions: window.StudyLibrary.list()});
    accountStatus(`${data.available_in_account} session links are available in your account. ${data.unavailable} could not be imported.`);
}));
$account('password-form').addEventListener('submit', event => {
    event.preventDefault();
    if ($account('new-password').value !== $account('confirm-new-password').value) { accountStatus('The replacement passwords do not match.'); return; }
    accountAction(async () => {
        await accountRequest('/account/password', 'POST', {current_password:$account('current-password').value, new_password:$account('new-password').value});
        $account('password-form').reset(); accountStatus('Password updated. Other browsers have been signed out.');
    });
});
if (window.location.protocol !== 'https:' && !['localhost','127.0.0.1','[::1]'].includes(window.location.hostname)) {
    accountStatus('Accounts require HTTPS outside local development. Open this site using HTTPS.');
} else {
    accountAction(async () => { showAccount(await accountRequest('/account/me')); accountStatus(''); });
}
