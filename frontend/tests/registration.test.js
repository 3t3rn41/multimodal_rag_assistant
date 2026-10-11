import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createApp, h, nextTick } from 'vue';
import { createPinia, setActivePinia } from 'pinia';
import { createMemoryHistory, createRouter, RouterView } from 'vue-router';
import LoginView from '../src/views/auth/LoginView.vue';
import { http } from '../src/api/http';
import { useAuthStore } from '../src/stores/auth';

const email = 'registration@example.invalid';
const password = 'password1';
const token = 'registration-test-handle-'.repeat(2);
const response = (overrides = {}) => ({ data: {
  registration_token: token, expires_in: 600, resend_after: 0,
  message: '如该邮箱可以注册，验证码已发送。', ...overrides,
} });
let app, host, router, pinia, post;

function deferred() {
  let resolve, reject;
  const promise = new Promise((done, fail) => { resolve = done; reject = fail; });
  return { promise, resolve, reject };
}
async function mountRegistration() {
  router = createRouter({ history: createMemoryHistory(), routes: [
    { path: '/login', component: LoginView },
    { path: '/', component: { render: () => h('h1', '欢迎页') } },
    { path: '/app/kbs', component: { render: () => h('h1', '知识库首页') } },
  ] });
  host = document.createElement('div'); document.body.appendChild(host);
  app = createApp({ render: () => h(RouterView) }); app.use(pinia); app.use(router);
  await router.push('/login?mode=register'); await router.isReady(); app.mount(host);
  await nextTick();
}
async function fill(selector, value) {
  const input = host.querySelector(selector);
  input.value = value; input.dispatchEvent(new Event('input', { bubbles: true }));
  await nextTick();
}
async function register(pass = password, confirmation = pass) {
  await fill('#email', email); await fill('#password', pass); await fill('#registration-confirm', confirmation);
  const form = host.querySelector('form');
  form.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
  await nextTick(); return form;
}
async function enterCode(value = '123456') {
  for (let i = 0; i < value.length; i++) await fill(`#registration-code-${i + 1}`, value[i]);
}
function displayedCode() { return [...host.querySelectorAll('.registration-code-cell')].map(input => input.value).join(''); }
function resendButton() { return host.querySelector('.auth-links button'); }
function submitCode() { host.querySelector('.registration-code-form').dispatchEvent(new Event('submit', { bubbles: true, cancelable: true })); }
async function sent() { await vi.waitFor(() => expect(host.textContent).toContain('验证码已发送')); }

beforeEach(() => {
  pinia = createPinia(); setActivePinia(pinia);
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() {} });
  post = vi.spyOn(http, 'post').mockResolvedValue(response());
});
afterEach(() => {
  app?.unmount(); app = null; document.body.replaceChildren();
  vi.useRealTimers(); vi.unstubAllGlobals();
});

describe('email registration', () => {
  it('opens and focuses the six code inputs before the registration request completes', async () => {
    const pending = deferred(); post.mockReturnValue(pending.promise);
    await mountRegistration(); await register();
    expect(host.querySelector('h1').textContent).toBe('验证你的邮箱');
    expect(host.querySelector('#email')).toBeNull();
    expect(host.querySelectorAll('.registration-code-cell')).toHaveLength(6);
    expect([...host.querySelectorAll('.registration-code-cell')].every(input => !input.disabled)).toBe(true);
    expect(document.activeElement.id).toBe('registration-code-1');
    expect(host.textContent).toContain('正在发送验证码…');
    expect(host.textContent).not.toContain('分钟内有效');
    expect(host.querySelector('.auth-submit').disabled).toBe(true);
    expect([...host.querySelectorAll('.auth-links button')].every(button => button.disabled)).toBe(true);
    expect(post).toHaveBeenCalledWith('/auth/register', { email, password }, { signal: expect.any(AbortSignal) });
    expect(useAuthStore().user).toBeNull();
    pending.resolve(response()); await sent();
  });

  it('preserves a code entered during sending and starts the returned cooldown after success', async () => {
    const pending = deferred(); post.mockReturnValue(pending.promise);
    await mountRegistration(); await register(); await enterCode();
    submitCode(); await nextTick(); expect(post).toHaveBeenCalledTimes(1);
    pending.resolve(response({ expires_in: 720, resend_after: 90 })); await sent();
    expect(displayedCode()).toBe('123456');
    expect(document.activeElement.id).toBe('registration-code-6');
    expect(host.querySelector('.auth-submit').disabled).toBe(false);
    expect(host.textContent).toContain('12 分钟内有效');
    expect(resendButton().textContent).toContain('90 秒后可重新发送');
  });

  it('ignores repeated registration and resend operations while sending', async () => {
    const pending = deferred(); post.mockReturnValue(pending.promise);
    await mountRegistration(); const oldForm = await register();
    oldForm.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    resendButton().dispatchEvent(new MouseEvent('click', { bubbles: true }));
    await enterCode(); submitCode(); await nextTick();
    expect(post).toHaveBeenCalledTimes(1);
    pending.resolve(response()); await sent();
  });

  it.each(['short', 'password!'])('keeps invalid passwords on the registration form: %s', async pass => {
    await mountRegistration(); await register(pass);
    expect(host.textContent).toContain('密码须为 8–20 个字符');
    expect(host.querySelector('#password')).not.toBeNull();
    expect(host.querySelector('.registration-code-form')).toBeNull(); expect(post).not.toHaveBeenCalled();
  });

  it('keeps a mismatched confirmation on the form', async () => {
    await mountRegistration(); await register(password, 'password2');
    expect(host.textContent).toContain('两次输入的密码不同');
    expect(host.querySelector('#registration-confirm')).not.toBeNull(); expect(post).not.toHaveBeenCalled();
  });

  it.each([
    ['network', { message: 'Network Error' }, '验证码发送失败'],
    ['timeout', { code: 'ECONNABORTED', message: 'timeout of 30000ms exceeded' }, '验证码发送失败'],
    ['service', { response: { status: 503, data: { error: { message: '邮件服务暂不可用' } } } }, '邮件服务暂不可用'],
    ['rate limit', { response: { status: 429, data: { error: { message: '操作过于频繁，请稍后重试。' } } } }, '操作过于频繁'],
  ])('keeps the code screen and offers retry after a %s error', async (_, error, text) => {
    post.mockRejectedValue(error); await mountRegistration(); await register();
    await vi.waitFor(() => expect(host.textContent).toContain(text));
    expect(host.querySelector('h1').textContent).toBe('验证你的邮箱');
    expect(resendButton().textContent).toBe('重试发送'); expect(resendButton().disabled).toBe(false);
    expect(host.querySelector('.auth-submit').disabled).toBe(true);
    expect(host.textContent).not.toMatch(/Network Error|timeout of|分钟内有效/);
    await enterCode(); submitCode(); await nextTick(); expect(post).toHaveBeenCalledTimes(1);
    expect(host.querySelector('[role=alert]').textContent).toContain(text);
  });

  it('retries an initial failure with the original credentials and preserves new input', async () => {
    const retry = deferred();
    post.mockRejectedValueOnce({ response: { status: 503 } }).mockReturnValueOnce(retry.promise);
    await mountRegistration(); await register();
    await vi.waitFor(() => expect(resendButton().textContent).toBe('重试发送'));
    resendButton().click(); await nextTick();
    expect(post.mock.calls[1].slice(0, 2)).toEqual(['/auth/register', { email, password }]);
    await enterCode('654321'); retry.resolve(response()); await sent();
    expect(displayedCode()).toBe('654321'); expect(host.querySelector('[role=alert]')).toBeNull();
    expect(resendButton().textContent).toBe('重新发送验证码');
  });

  it.each([undefined, null, '', 'short', ' '.repeat(32), 'a'.repeat(129)])('does not enable verification for an invalid handle: %s', async handle => {
    post.mockResolvedValue(response({ registration_token: handle }));
    await mountRegistration(); await register();
    await vi.waitFor(() => expect(host.textContent).toContain('验证码发送响应无效'));
    await enterCode(); submitCode(); await nextTick();
    expect(host.querySelector('.auth-submit').disabled).toBe(true);
    expect(resendButton().textContent).toBe('重试发送'); expect(post).toHaveBeenCalledTimes(1);
  });

  it('clears failed registration information when returning to edit the form', async () => {
    post.mockRejectedValue({ response: { status: 503 } });
    await mountRegistration(); await register();
    await vi.waitFor(() => expect(resendButton().textContent).toBe('重试发送'));
    host.querySelectorAll('.auth-links button')[1].click(); await nextTick();
    expect(host.querySelector('#email').value).toBe(email);
    expect(host.querySelector('#password').value).toBe('');
    expect(host.querySelector('#registration-confirm').value).toBe('');
    expect(host.querySelector('[role=alert]')).toBeNull();
    post.mockResolvedValue(response()); await register('newpass12'); await sent();
    expect(post.mock.calls[1].slice(0, 2)).toEqual(['/auth/register', { email, password: 'newpass12' }]);
  });

  it('verifies once with the handle and only then displays registration success', async () => {
    const verification = deferred(); post.mockResolvedValueOnce(response()).mockReturnValueOnce(verification.promise);
    await mountRegistration(); await register(); await sent(); await enterCode();
    submitCode(); submitCode(); await nextTick();
    expect(post).toHaveBeenCalledTimes(2);
    expect(post.mock.calls[1]).toEqual(['/auth/verify-registration', { email, registration_token: token, code: '123456' }, { signal: expect.any(AbortSignal) }]);
    expect([...host.querySelectorAll('.registration-code-cell')].every(input => input.disabled)).toBe(true);
    expect(host.textContent).toContain('正在验证…');
    verification.resolve({ data: { message: '注册成功' } });
    await vi.waitFor(() => expect(host.querySelector('h1').textContent).toBe('注册成功'));
    expect(useAuthStore().user).toBeNull();
    host.querySelector('.auth-submit').click(); await nextTick();
    expect(host.querySelector('h1').textContent).toBe('欢迎回来'); expect(host.querySelector('#password').value).toBe('');
  });

  it('clears verification errors when the code changes', async () => {
    post.mockResolvedValueOnce(response()).mockRejectedValueOnce({ response: { status: 400, data: { error: { message: '验证码不正确' } } } });
    await mountRegistration(); await register(); await sent(); await enterCode(); submitCode();
    await vi.waitFor(() => expect(host.textContent).toContain('验证码不正确'));
    expect(host.querySelector('.registration-code-cell').getAttribute('aria-invalid')).toBe('true');
    await fill('#registration-code-1', '9');
    expect(host.querySelector('[role=alert]')).toBeNull();
    expect(host.querySelector('.registration-code-cell').hasAttribute('aria-invalid')).toBe(false);
  });

  it('enforces the successful resend cooldown and uses the handle for the next request', async () => {
    const pending = deferred();
    await mountRegistration(); vi.useFakeTimers();
    post.mockResolvedValueOnce(response({ resend_after: 60 })).mockReturnValueOnce(pending.promise);
    await register(); await sent(); await enterCode();
    resendButton().click(); expect(post).toHaveBeenCalledTimes(1);
    vi.advanceTimersByTime(59_000); await nextTick();
    expect(resendButton().textContent).toContain('1 秒后可重新发送'); expect(resendButton().disabled).toBe(true);
    vi.advanceTimersByTime(1_000); await nextTick(); resendButton().click(); await nextTick();
    expect(post.mock.calls[1].slice(0, 2)).toEqual(['/auth/resend-verification', { email, registration_token: token }]);
    expect(displayedCode()).toBe('');
    await enterCode('654321'); pending.resolve({ data: { message: '新的验证码已发送', resend_after: 60 } }); await sent();
    expect(displayedCode()).toBe('654321'); expect(resendButton().disabled).toBe(true);
  });

  it('keeps resend failures visible while allowing another resend with the same handle', async () => {
    post.mockResolvedValueOnce(response()).mockRejectedValueOnce({ response: { status: 503, data: { error: { message: '邮件服务暂不可用' } } } }).mockResolvedValueOnce(response());
    await mountRegistration(); await register(); await sent(); resendButton().click();
    await vi.waitFor(() => expect(host.textContent).toContain('邮件服务暂不可用'));
    expect(resendButton().textContent).toBe('重新发送验证码'); await enterCode();
    expect(host.querySelector('[role=alert]').textContent).toContain('邮件服务暂不可用');
    resendButton().click(); await sent();
    expect(post.mock.calls[2].slice(0, 2)).toEqual(['/auth/resend-verification', { email, registration_token: token }]);
  });

  it('resets the previous cooldown when registration information is changed', async () => {
    post.mockResolvedValueOnce(response({ resend_after: 60 })).mockRejectedValueOnce({ response: { status: 503 } });
    await mountRegistration(); await register(); await sent();
    host.querySelectorAll('.auth-links button')[1].click(); await nextTick(); await register('newpass12');
    await vi.waitFor(() => expect(host.textContent).toContain('验证码发送失败'));
    expect(resendButton().textContent).toBe('重试发送'); expect(resendButton().disabled).toBe(false);
  });

  it.each(['register', 'resend', 'verify'])('aborts a pending %s request on departure and ignores a late success', async phase => {
    const pending = deferred();
    post.mockImplementation(url => phase === 'register' || (phase === 'resend' && url === '/auth/resend-verification') || url === '/auth/verify-registration'
      ? pending.promise : Promise.resolve(response()));
    await mountRegistration(); await register();
    if (phase !== 'register') await sent();
    if (phase === 'resend') { resendButton().click(); await nextTick(); }
    if (phase === 'verify') { await enterCode(); submitCode(); await nextTick(); }
    const signal = post.mock.calls.at(-1)[2].signal;
    await router.push('/'); await nextTick(); expect(signal.aborted).toBe(true);
    const interval = vi.spyOn(globalThis, 'setInterval'); pending.resolve(response());
    await Promise.resolve(); await nextTick();
    expect(host.querySelector('h1').textContent).toBe('欢迎页'); expect(interval).not.toHaveBeenCalled();
    await router.push('/login?mode=register'); await nextTick();
    expect(host.querySelector('#password').value).toBe(''); expect(host.querySelector('.registration-code-form')).toBeNull();
  });

  it('ignores a late sending failure after leaving the page', async () => {
    const pending = deferred(); post.mockReturnValue(pending.promise);
    await mountRegistration(); await register(); await router.push('/');
    pending.reject({ response: { status: 503, data: { error: { message: '迟到错误' } } } });
    await Promise.resolve(); await nextTick();
    expect(host.querySelector('[role=alert]')).toBeNull(); expect(host.textContent).not.toContain('迟到错误');
  });
});
