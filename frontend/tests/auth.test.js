import { beforeEach, describe, expect, it, vi } from "vitest";
import { createPinia, setActivePinia } from "pinia";
import { http } from "../src/api/http";
import { useAuthStore } from "../src/stores/auth";

beforeEach(() => setActivePinia(createPinia()));

describe("email account sessions", () => {
  it("initializes from the current session without a mode configuration request", async () => {
    const user = { id: 7, email: "user@example.invalid" };
    const get = vi.spyOn(http, "get").mockResolvedValue({ data: user });
    const auth = useAuthStore();
    await auth.init();
    expect(auth.user).toEqual(user);
    expect(auth.loaded).toBe(true);
    expect(auth.$state).not.toHaveProperty("config");
    expect(get).toHaveBeenCalledTimes(1);
    expect(get).toHaveBeenCalledWith("/auth/me");
  });

  it("does not invent a local account when the session is missing", async () => {
    vi.spyOn(http, "get").mockRejectedValue({ response: { status: 401 } });
    const auth = useAuthStore();
    await auth.init();
    expect(auth.user).toBeNull();
    expect(auth.loaded).toBe(true);
    expect(auth.error).toBeNull();
  });

  it("keeps service failures distinct from missing sessions", async () => {
    vi.spyOn(http, "get").mockRejectedValue({ response: { status: 503, data: { error: { message: "Service unavailable" } } } });
    const auth = useAuthStore();
    await auth.init();
    expect(auth.user).toBeNull();
    expect(auth.loaded).toBe(false);
    expect(auth.error).toBe("Service unavailable");
  });

  it("shares one initialization request across simultaneous callers", async () => {
    let resolve;
    const get = vi.spyOn(http, "get").mockImplementation(() => new Promise(done => { resolve = done; }));
    const auth = useAuthStore();
    const first = auth.init();
    const second = auth.init();
    resolve({ data: { id: 7, email: "user@example.invalid" } });
    await Promise.all([first, second]);
    expect(get).toHaveBeenCalledTimes(1);
    expect(auth.loaded).toBe(true);
  });

  it('retries account initialization after a network failure', async () => {
    const user = {id: 7, email: 'user@example.invalid'};
    vi.spyOn(http, 'get').mockRejectedValueOnce({message: 'Network Error'}).mockResolvedValueOnce({data: user});
    const auth = useAuthStore(); await auth.init();
    expect(auth.loaded).toBe(false); expect(auth.error).toContain('读取失败');
    await auth.init(); expect(auth.user).toEqual(user); expect(auth.loaded).toBe(true); expect(auth.error).toBeNull();
  });

  it('does not show an old account request cancellation as a login failure', async () => {
    let reject;
    vi.spyOn(http, 'get').mockImplementation(() => new Promise((_, fail) => {reject = fail}));
    const auth = useAuthStore(), pending = auth.init();
    auth.clearAccount(); auth.user = {id: 8, email: 'new@example.invalid'}; auth.loaded = true;
    reject({code: 'ERR_CANCELED'}); await pending;
    expect(auth.error).toBeNull(); expect(auth.user.id).toBe(8); expect(auth.loaded).toBe(true);
  });

  it("clears the account when logout reports an expired session", async () => {
    vi.spyOn(http, "post").mockRejectedValue({ response: { status: 401 } });
    const auth = useAuthStore();
    auth.user = { id: 7, email: "user@example.invalid" };
    await auth.logout();
    expect(auth.user).toBeNull();
  });
});

