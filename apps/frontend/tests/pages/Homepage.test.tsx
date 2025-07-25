import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import Homepage from '../../src/pages/Homepage';

// Top-level mock setup
vi.mock('../../src/state/auth', () => ({
  useAuth: vi.fn(),
}));

import { useAuth } from '../../src/state/auth'; // Must be after the mock

describe('Homepage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders login prompt when user is not logged in', () => {
    vi.mocked(useAuth).mockReturnValue({ user: null });
    render(<Homepage />);
    expect(screen.getByText(/Welcome! Please login to continue/i)).toBeInTheDocument();
  });

  it('renders success message when user is logged in', () => {
    vi.mocked(useAuth).mockReturnValue({ user: { id: 1, username: 'testuser' } });
    render(<Homepage />);
    expect(screen.getByText(/Success! You are logged in/i)).toBeInTheDocument();
  });
});
