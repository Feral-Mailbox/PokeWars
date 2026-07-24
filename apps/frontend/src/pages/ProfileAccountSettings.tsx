import { useState, type FormEvent } from 'react';
import { secureFetch } from '@/utils/secureFetch';
import type { User } from '../types/user';

type ProfileAccountSettingsProps = {
  email: string;
  onUserUpdated: (user: User) => void;
};

function apiErrorMessage(payload: unknown, fallback: string): string {
  if (!payload || typeof payload !== 'object') return fallback;
  const detail = (payload as { detail?: unknown }).detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0];
    if (first && typeof first === 'object' && 'msg' in first) {
      return String((first as { msg: unknown }).msg);
    }
  }
  return fallback;
}

const fieldClass =
  'w-full rounded border border-gray-600 bg-gray-900 px-3 py-2 text-sm text-white placeholder:text-gray-500 focus:border-blue-500 focus:outline-none';
const labelClass = 'mb-1 block text-xs font-medium uppercase tracking-wide text-gray-400';
const buttonClass =
  'rounded bg-blue-600 px-3 py-2 text-sm font-medium text-white hover:bg-blue-500 disabled:cursor-not-allowed disabled:opacity-60';

export function ProfileAccountSettings({ email, onUserUpdated }: ProfileAccountSettingsProps) {
  const [emailValue, setEmailValue] = useState(email);
  const [emailPassword, setEmailPassword] = useState('');
  const [emailStatus, setEmailStatus] = useState<{ type: 'error' | 'success'; text: string } | null>(
    null,
  );
  const [emailBusy, setEmailBusy] = useState(false);

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordStatus, setPasswordStatus] = useState<
    { type: 'error' | 'success'; text: string } | null
  >(null);
  const [passwordBusy, setPasswordBusy] = useState(false);

  const handleEmailSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setEmailStatus(null);
    setEmailBusy(true);
    try {
      const res = await secureFetch('/api/me/email', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: emailValue.trim(),
          current_password: emailPassword,
        }),
      });
      if (!res) {
        setEmailStatus({ type: 'error', text: 'Could not update email.' });
        return;
      }
      const payload = await res.json().catch(() => null);
      if (!res.ok) {
        setEmailStatus({
          type: 'error',
          text: apiErrorMessage(payload, 'Could not update email.'),
        });
        return;
      }
      onUserUpdated(payload as User);
      setEmailPassword('');
      setEmailStatus({ type: 'success', text: 'Email updated.' });
    } catch {
      setEmailStatus({ type: 'error', text: 'Could not update email.' });
    } finally {
      setEmailBusy(false);
    }
  };

  const handlePasswordSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setPasswordStatus(null);

    if (newPassword !== confirmPassword) {
      setPasswordStatus({ type: 'error', text: 'New passwords do not match.' });
      return;
    }
    if (newPassword.length < 8) {
      setPasswordStatus({ type: 'error', text: 'New password must be at least 8 characters.' });
      return;
    }

    setPasswordBusy(true);
    try {
      const res = await secureFetch('/api/me/password', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      if (!res) {
        setPasswordStatus({ type: 'error', text: 'Could not update password.' });
        return;
      }
      const payload = await res.json().catch(() => null);
      if (!res.ok) {
        setPasswordStatus({
          type: 'error',
          text: apiErrorMessage(payload, 'Could not update password.'),
        });
        return;
      }
      onUserUpdated(payload as User);
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
      setPasswordStatus({ type: 'success', text: 'Password updated.' });
    } catch {
      setPasswordStatus({ type: 'error', text: 'Could not update password.' });
    } finally {
      setPasswordBusy(false);
    }
  };

  return (
    <section className="mt-8 space-y-6">
      <h2 className="text-xl font-semibold text-white">Account settings</h2>

      <form
        onSubmit={handleEmailSubmit}
        className="rounded-lg border border-gray-700 bg-gray-800/80 p-5"
        noValidate
      >
        <h3 className="text-sm font-semibold text-white">Change email</h3>
        <p className="mt-1 text-sm text-gray-400">Confirm with your current password.</p>
        <div className="mt-4 grid gap-3 sm:grid-cols-2">
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="profile-email">
              Email
            </label>
            <input
              id="profile-email"
              className={fieldClass}
              type="email"
              autoComplete="email"
              value={emailValue}
              onChange={(e) => setEmailValue(e.target.value)}
              required
            />
          </div>
          <div className="sm:col-span-2">
            <label className={labelClass} htmlFor="profile-email-password">
              Confirm password
            </label>
            <input
              id="profile-email-password"
              className={fieldClass}
              type="password"
              autoComplete="current-password"
              value={emailPassword}
              onChange={(e) => setEmailPassword(e.target.value)}
              required
            />
          </div>
        </div>
        {emailStatus ? (
          <p
            className={`mt-3 text-sm ${emailStatus.type === 'error' ? 'text-red-400' : 'text-green-400'}`}
            role="status"
          >
            {emailStatus.text}
          </p>
        ) : null}
        <button type="submit" className={`${buttonClass} mt-4`} disabled={emailBusy}>
          {emailBusy ? 'Saving…' : 'Update email'}
        </button>
      </form>

      <form
        onSubmit={handlePasswordSubmit}
        className="rounded-lg border border-gray-700 bg-gray-800/80 p-5"
        noValidate
      >
        <h3 className="text-sm font-semibold text-white">Change password</h3>
        <p className="mt-1 text-sm text-gray-400">Use at least 8 characters for the new password.</p>
        <div className="mt-4 grid gap-3">
          <div>
            <label className={labelClass} htmlFor="profile-current-password">
              Current password
            </label>
            <input
              id="profile-current-password"
              className={fieldClass}
              type="password"
              autoComplete="current-password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              required
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="profile-new-password">
              New password
            </label>
            <input
              id="profile-new-password"
              className={fieldClass}
              type="password"
              autoComplete="new-password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              required
              minLength={8}
            />
          </div>
          <div>
            <label className={labelClass} htmlFor="profile-confirm-password">
              Confirm new password
            </label>
            <input
              id="profile-confirm-password"
              className={fieldClass}
              type="password"
              autoComplete="new-password"
              value={confirmPassword}
              onChange={(e) => setConfirmPassword(e.target.value)}
              required
              minLength={8}
            />
          </div>
        </div>
        {passwordStatus ? (
          <p
            className={`mt-3 text-sm ${passwordStatus.type === 'error' ? 'text-red-400' : 'text-green-400'}`}
            role="status"
          >
            {passwordStatus.text}
          </p>
        ) : null}
        <button type="submit" className={`${buttonClass} mt-4`} disabled={passwordBusy}>
          {passwordBusy ? 'Saving…' : 'Update password'}
        </button>
      </form>
    </section>
  );
}
