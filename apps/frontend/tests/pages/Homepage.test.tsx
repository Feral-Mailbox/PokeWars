import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import Homepage from '../../src/pages/Homepage';

vi.mock('../../src/state/auth', () => ({
  useAuth: vi.fn(),
}));

vi.mock('../../src/utils/secureFetch', () => ({
  secureFetch: vi.fn(),
}));

import { useAuth } from '../../src/state/auth';
import { secureFetch } from '../../src/utils/secureFetch';

const mockRequestAuthPrompt = vi.fn();

const loggedInUser = {
  id: 1,
  username: 'testuser',
  email: 'test@example.com',
  avatar: '',
  elo: 1000,
  currency: 0,
  role: 'user' as const,
};

describe('Homepage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders login prompt when user is not logged in', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      requestAuthPrompt: mockRequestAuthPrompt,
    } as ReturnType<typeof useAuth>);

    render(
      <MemoryRouter>
        <Homepage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: /PokéTactics/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Log in/i })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /Create account/i })).toBeInTheDocument();
  });

  it('opens auth prompts from logged-out CTAs', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      requestAuthPrompt: mockRequestAuthPrompt,
    } as ReturnType<typeof useAuth>);

    render(
      <MemoryRouter>
        <Homepage />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /Log in/i }));
    expect(mockRequestAuthPrompt).toHaveBeenCalledWith('login');

    fireEvent.click(screen.getByRole('button', { name: /Create account/i }));
    expect(mockRequestAuthPrompt).toHaveBeenCalledWith('register');
  });

  it('renders dashboard when user is logged in', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: loggedInUser,
      loading: false,
      requestAuthPrompt: mockRequestAuthPrompt,
    } as ReturnType<typeof useAuth>);

    render(
      <MemoryRouter>
        <Homepage />
      </MemoryRouter>,
    );

    expect(screen.getByText(/Welcome back, testuser/i)).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /Create Game/i })).toHaveAttribute('href', '/games/create');
    expect(screen.getByRole('link', { name: /Join Game/i })).toHaveAttribute('href', '/games/join');
  });

  it('navigates to a pasted game link after the backend confirms it exists', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: loggedInUser,
      loading: false,
      requestAuthPrompt: mockRequestAuthPrompt,
    } as ReturnType<typeof useAuth>);
    vi.mocked(secureFetch).mockResolvedValue({ ok: true } as Response);

    render(
      <MemoryRouter>
        <Homepage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText(/Paste link or game ID/i), {
      target: { value: 'abc123' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Go$/i }));

    await waitFor(() => {
      expect(window.location.pathname).toBe('/games/abc123');
    });
    expect(secureFetch).toHaveBeenCalledWith('/api/games/abc123');
  });

  it('shows a toast when the pasted link format is invalid', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: loggedInUser,
      loading: false,
      requestAuthPrompt: mockRequestAuthPrompt,
    } as ReturnType<typeof useAuth>);

    render(
      <MemoryRouter>
        <Homepage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText(/Paste link or game ID/i), {
      target: { value: 'not a valid link!!!' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Go$/i }));

    expect(screen.getByRole('alert')).toHaveTextContent(/Enter a valid game link or ID/i);
    expect(secureFetch).not.toHaveBeenCalled();
  });

  it('shows a toast when the backend reports the game does not exist', async () => {
    vi.mocked(useAuth).mockReturnValue({
      user: loggedInUser,
      loading: false,
      requestAuthPrompt: mockRequestAuthPrompt,
    } as ReturnType<typeof useAuth>);
    vi.mocked(secureFetch).mockResolvedValue({ ok: false } as Response);

    render(
      <MemoryRouter>
        <Homepage />
      </MemoryRouter>,
    );

    fireEvent.change(screen.getByPlaceholderText(/Paste link or game ID/i), {
      target: { value: '2' },
    });
    fireEvent.click(screen.getByRole('button', { name: /^Go$/i }));

    await waitFor(() => {
      expect(screen.getByRole('alert')).toHaveTextContent(/Game not found/i);
    });
    expect(window.location.pathname).not.toBe('/games/2');
  });

  it('shows a toast passed from router state after redirect', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: loggedInUser,
      loading: false,
      requestAuthPrompt: mockRequestAuthPrompt,
    } as ReturnType<typeof useAuth>);

    render(
      <MemoryRouter initialEntries={[{ pathname: '/', state: { toastMessage: 'Game not found. Check the link and try again.' } }]}>
        <Homepage />
      </MemoryRouter>,
    );

    expect(screen.getByRole('alert')).toHaveTextContent(/Game not found/i);
  });
});
