// tests/components/Navbar.test.tsx

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import Navbar from '@/components/Navbar';

// Mock react-router-dom's useNavigate
vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom');
  return {
    ...actual,
    useNavigate: () => vi.fn(),
  };
});

// Inline mock for secureFetch (to avoid hoisting issues)
vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn(),
}));

// Now we can safely import secureFetch
import { secureFetch } from '@/utils/secureFetch';

// Mock useAuth
vi.mock('@/state/auth', () => {
  return {
    useAuth: () => ({
      user: null,
      setUser: vi.fn(),
    }),
  };
});

describe('Navbar', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the logo and nav buttons', async () => {
    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    expect(screen.getByAltText(/logo/i)).toBeInTheDocument();
    expect(screen.getByText(/Games/i)).toBeInTheDocument();
    expect(screen.getByText(/Login/i)).toBeInTheDocument();
  });

  it('fetches user session on mount', async () => {
    (secureFetch as vi.Mock).mockResolvedValueOnce({
      id: 1,
      username: 'testuser',
    });

    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith('/api/me');
    });
  });

  it('handles secureFetch failure gracefully', async () => {
    (secureFetch as vi.Mock).mockRejectedValueOnce(new Error('Network error'));

    render(
      <MemoryRouter>
        <Navbar />
      </MemoryRouter>
    );

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith('/api/me');
    });
  });
});
