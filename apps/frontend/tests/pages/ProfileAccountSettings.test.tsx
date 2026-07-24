import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { ProfileAccountSettings } from '@/pages/ProfileAccountSettings';
import type { User } from '@/types/user';

vi.mock('@/utils/secureFetch', () => ({
  secureFetch: vi.fn(),
}));

import { secureFetch } from '@/utils/secureFetch';

const baseUser: User = {
  id: 1,
  trainer_id: '214D27D0',
  username: 'anorgandroid',
  email: 'anorgandroid@gmail.com',
  avatar: 'default.png',
  elo_conquest: 1000,
  elo_war: 1000,
  currency: 0,
  role: 'admin',
};

describe('ProfileAccountSettings', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('updates email with current password', async () => {
    const onUserUpdated = vi.fn();
    const user = userEvent.setup();
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => ({ ...baseUser, email: 'new@example.com' }),
    } as Response);

    render(
      <ProfileAccountSettings email={baseUser.email} onUserUpdated={onUserUpdated} />,
    );

    await user.clear(screen.getByLabelText(/^email$/i));
    await user.type(screen.getByLabelText(/^email$/i), 'new@example.com');
    await user.type(screen.getByLabelText(/^confirm password$/i), 'secretpw');
    await user.click(screen.getByRole('button', { name: /update email/i }));

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith('/api/me/email', expect.objectContaining({
        method: 'PATCH',
      }));
      expect(onUserUpdated).toHaveBeenCalled();
      expect(screen.getByText('Email updated.')).toBeInTheDocument();
    });
  });

  it('updates password when confirmation matches', async () => {
    const onUserUpdated = vi.fn();
    const user = userEvent.setup();
    vi.mocked(secureFetch).mockResolvedValue({
      ok: true,
      status: 200,
      json: async () => baseUser,
    } as Response);

    render(
      <ProfileAccountSettings email={baseUser.email} onUserUpdated={onUserUpdated} />,
    );

    await user.type(screen.getByLabelText(/^current password$/i), 'oldsecret');
    await user.type(screen.getByLabelText(/^new password$/i), 'newsecret1');
    await user.type(screen.getByLabelText(/confirm new password/i), 'newsecret1');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    await waitFor(() => {
      expect(secureFetch).toHaveBeenCalledWith('/api/me/password', expect.objectContaining({
        method: 'PATCH',
      }));
      expect(screen.getByText('Password updated.')).toBeInTheDocument();
    });
  });

  it('rejects mismatched password confirmation client-side', async () => {
    const user = userEvent.setup();
    render(
      <ProfileAccountSettings email={baseUser.email} onUserUpdated={vi.fn()} />,
    );

    await user.type(screen.getByLabelText(/^current password$/i), 'oldsecret');
    await user.type(screen.getByLabelText(/^new password$/i), 'newsecret1');
    await user.type(screen.getByLabelText(/confirm new password/i), 'different1');
    await user.click(screen.getByRole('button', { name: /update password/i }));

    expect(screen.getByText('New passwords do not match.')).toBeInTheDocument();
    expect(secureFetch).not.toHaveBeenCalled();
  });
});
