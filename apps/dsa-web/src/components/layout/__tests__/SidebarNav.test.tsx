import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { SidebarNav } from '../SidebarNav';

const mockLogout = vi.fn().mockResolvedValue(undefined);
const mockThemeToggle = vi.fn(({ collapsed }: { collapsed?: boolean }) => (
  <button type="button">{collapsed ? '切换主题(折叠)' : '切换主题'}</button>
));

vi.mock('../../../contexts/AuthContext', () => ({
  useAuth: () => ({
    authEnabled: true,
    logout: mockLogout,
  }),
}));

vi.mock('../../theme/ThemeToggle', () => ({
  ThemeToggle: (props: { collapsed?: boolean }) => mockThemeToggle(props),
}));

describe('SidebarNav', () => {
  it('shows only the requested navigation links', () => {
    render(<MemoryRouter initialEntries={['/']}><SidebarNav /></MemoryRouter>);
    const hrefs = screen.getAllByRole('link').map((link) => link.getAttribute('href'));
    expect(hrefs).toEqual(['/', '/portfolio', '/new-highs', '/alerts', '/data', '/usage', '/settings']);
    expect(screen.getByRole('button', { name: '切换主题' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: '退出' })).toBeInTheDocument();
  });

  it('renders the collapsed theme toggle variant when the sidebar is collapsed', () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <SidebarNav collapsed />
      </MemoryRouter>,
    );

    expect(mockThemeToggle).toHaveBeenCalledWith(
      expect.objectContaining({ variant: 'nav', collapsed: true }),
    );
    expect(screen.getByRole('button', { name: '切换主题(折叠)' })).toBeInTheDocument();
  });

  it('renders the alerts navigation item and marks it active', () => {
    render(
      <MemoryRouter initialEntries={['/alerts']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const alertsLink = screen.getByRole('link', { name: '告警' });
    expect(alertsLink).toHaveAttribute('href', '/alerts');
    expect(alertsLink).toHaveClass('font-medium');
  });

  it('renders the data center navigation item and marks it active', () => {
    render(
      <MemoryRouter initialEntries={['/data']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    const link = screen.getByRole('link', { name: '数据中心' });
    expect(link).toHaveAttribute('href', '/data');
    expect(link).toHaveClass('font-medium');
  });

  it('keeps rail controls outside the scrollable navigation links', () => {
    render(<MemoryRouter><SidebarNav variant="rail" /></MemoryRouter>);

    const nav = screen.getByRole('navigation', { name: '主导航' });
    expect(nav).toHaveClass('min-h-0', 'overflow-y-auto');
    expect(nav).not.toContainElement(screen.getByRole('button', { name: '退出' }));
    expect(nav).not.toContainElement(screen.getByRole('button', { name: '切换主题' }));
    expect(screen.getByRole('link', { name: '设置' })).toHaveClass('shrink-0');
  });

  it.each(['/settings?category=system', '/settings/'])(
    'explicitly confirms settings draft loss before logout at %s', async (path) => {
      mockLogout.mockClear();
      render(<MemoryRouter initialEntries={[path]}><SidebarNav /></MemoryRouter>);
      fireEvent.click(screen.getByRole('button', { name: '退出' }));
      expect(await screen.findByText(/退出会丢弃本页未保存的设置/)).toBeInTheDocument();
      expect(screen.getByText(/已发出的保存请求不会因退出而撤销/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole('button', { name: '取消' }));
      expect(mockLogout).not.toHaveBeenCalled();
      fireEvent.click(screen.getByRole('button', { name: '退出' }));
      fireEvent.click(screen.getByRole('button', { name: '确认退出' }));
      expect(mockLogout).toHaveBeenCalledTimes(1);
    },
  );

  it('opens the logout confirmation and confirms logout', async () => {
    render(
      <MemoryRouter initialEntries={['/chat']}>
        <SidebarNav />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: '退出' }));

    expect(await screen.findByRole('heading', { name: '退出登录' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: '确认退出' }));
    expect(mockLogout).toHaveBeenCalled();
  });
});
