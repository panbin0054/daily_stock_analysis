import { fireEvent, render, screen } from '@testing-library/react';
import type { ReactNode } from 'react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import App from './App';
import * as AuthContext from './contexts/AuthContext';
import { UI_LANGUAGE_STORAGE_KEY } from './utils/uiLanguage';

type AuthState = ReturnType<typeof AuthContext.useAuth>;

const { routePageShouldThrow } = vi.hoisted(() => ({ routePageShouldThrow: { value: false } }));

vi.mock('./contexts/AuthContext', () => ({
  AuthProvider: ({ children }: { children: ReactNode }) => children,
  useAuth: vi.fn(),
}));

vi.mock('./pages/HomePage', () => ({
  default: () => <div data-testid="home-page">Home</div>,
}));

vi.mock('./pages/PortfolioPage', () => ({
  default: () => {
    if (routePageShouldThrow.value) throw new Error('chunk load failed');
    return <div data-testid="portfolio-page">Portfolio</div>;
  },
}));

vi.mock('./pages/DecisionSignalsPage', () => ({
  default: () => <div data-testid="decision-signals-page">Decision signals</div>,
}));

vi.mock('./pages/BacktestPage', () => ({
  default: () => <div data-testid="backtest-page">Backtest</div>,
}));

vi.mock('./pages/AlertsPage', () => ({
  default: () => <div data-testid="alerts-page">Alerts</div>,
}));

vi.mock('./pages/TokenUsagePage', () => ({
  default: () => <div data-testid="token-usage-page">Usage</div>,
}));

vi.mock('./pages/SettingsPage', () => ({
  default: () => <div data-testid="settings-page">Settings</div>,
}));

vi.mock('./pages/DataCenterPage', () => ({
  default: () => <div data-testid="data-center-page">Data center</div>,
}));

vi.mock('./pages/NotFoundPage', () => ({
  default: () => <div data-testid="not-found-page">Not Found</div>,
}));

vi.mock('./pages/LoginPage', () => ({
  default: () => <div data-testid="login-page">Login</div>,
}));

function makeAuthState(overrides: Partial<AuthState> = {}): AuthState {
  return {
    authEnabled: false,
    loggedIn: false,
    passwordSet: false,
    passwordChangeable: false,
    setupState: 'no_password',
    isLoading: false,
    loadError: null,
    login: vi.fn().mockResolvedValue({ success: true }),
    changePassword: vi.fn().mockResolvedValue({ success: true }),
    logout: vi.fn().mockResolvedValue(undefined),
    refreshStatus: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  };
}

beforeEach(() => {
  vi.clearAllMocks();
  routePageShouldThrow.value = false;
  window.history.pushState({}, '', '/');
  localStorage.setItem(UI_LANGUAGE_STORAGE_KEY, 'zh');
  vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState());
});

describe('App routing behavior', () => {
  it('shows loading fallback while auth status is initializing', () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({ isLoading: true }));

    const { container } = render(<App />);

    expect(container.querySelector('.border-t-cyan')).toBeInTheDocument();
  });

  it('redirects protected routes to login when auth is enabled but user is not logged in', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: false,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/portfolio');

    render(<App />);

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(window.location.search).toBe('?redirect=%2Fportfolio');
  });

  it('renders the current route page after auth is ready', async () => {
    window.history.pushState({}, '', '/portfolio');

    render(<App />);

    expect(await screen.findByTestId('portfolio-page')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
    expect(screen.queryByTestId('home-page')).not.toBeInTheDocument();
  });

  it('preserves the query and fragment when redirecting a protected deep link to login', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: false,
      setupState: 'enabled',
    }));
    const destination = '/settings?category=system#desktop-version-info';
    window.history.pushState({}, '', destination);

    render(<App />);

    expect(await screen.findByTestId('login-page')).toBeInTheDocument();
    expect(window.location.pathname).toBe('/login');
    expect(new URLSearchParams(window.location.search).get('redirect')).toBe(destination);
    expect(window.location.hash).toBe('');
  });

  it('uses the safe deep link when auth resolves before the login page can navigate', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    const destination = '/settings?category=system#desktop-version-info';
    window.history.pushState({}, '', `/login?redirect=${encodeURIComponent(destination)}`);

    render(<App />);

    expect(await screen.findByTestId('settings-page')).toBeInTheDocument();
    expect(window.location.pathname + window.location.search + window.location.hash).toBe(destination);
    expect(screen.queryByTestId('home-page')).not.toBeInTheDocument();
  });

  it.each([
    'https://external.example/settings',
    '//external.example/settings',
    '/\\external.example/settings',
    '/%5cexternal.example/settings',
    '/%2fexternal.example/settings',
    '/..//external.example/settings',
    '/\t/external.example/settings',
    '/login?redirect=%2Fsettings',
    '/LOGIN/',
  ])('falls back to home for unsafe or looping login redirect %s', async (destination) => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    const origin = window.location.origin;
    window.history.pushState({}, '', `/login?redirect=${encodeURIComponent(destination)}`);

    render(<App />);

    expect(await screen.findByTestId('home-page')).toBeInTheDocument();
    expect(window.location.origin).toBe(origin);
    expect(window.location.pathname + window.location.search + window.location.hash).toBe('/');
  });

  it('routes /usage to the token usage page after auth is ready', async () => {
    window.history.pushState({}, '', '/usage');

    render(<App />);

    expect(await screen.findByTestId('token-usage-page')).toBeInTheDocument();
    expect(screen.queryByTestId('home-page')).not.toBeInTheDocument();
  });

  it.each(['/chat', '/screening', '/decision-signals', '/backtest'])(
    'does not expose the removed route %s', async (path) => {
      window.history.pushState({}, '', path);
      render(<App />);
      expect(await screen.findByTestId('not-found-page')).toBeInTheDocument();
    },
  );

  it('routes /data to the data capability page after auth is ready', async () => {
    window.history.pushState({}, '', '/data');

    render(<App />);

    expect(await screen.findByTestId('data-center-page')).toBeInTheDocument();
  });

  it('redirects authenticated login visits back to the home page', async () => {
    vi.mocked(AuthContext.useAuth).mockReturnValue(makeAuthState({
      authEnabled: true,
      loggedIn: true,
      setupState: 'enabled',
    }));
    window.history.pushState({}, '', '/login');

    render(<App />);

    expect(await screen.findByTestId('home-page')).toBeInTheDocument();
    expect(screen.queryByTestId('login-page')).not.toBeInTheDocument();
  });

  it('keeps the shell mounted and resets the route boundary after page render errors', async () => {
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => undefined);
    routePageShouldThrow.value = true;
    window.history.pushState({}, '', '/portfolio');

    try {
      render(<App />);

      expect(await screen.findByRole('heading', { name: '页面加载失败' })).toBeInTheDocument();
      expect(screen.getByRole('navigation', { name: '主导航' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '重新加载页面' })).toBeInTheDocument();
      expect(screen.getByRole('button', { name: '返回首页' })).toBeInTheDocument();

      routePageShouldThrow.value = false;
      fireEvent.click(screen.getByRole('link', { name: '首页' }));

      expect(await screen.findByTestId('home-page')).toBeInTheDocument();
      expect(screen.queryByRole('heading', { name: '页面加载失败' })).not.toBeInTheDocument();
    } finally {
      consoleError.mockRestore();
    }
  });
});
