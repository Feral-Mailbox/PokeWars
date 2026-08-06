import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import ReportBug from '@/pages/ReportBug';

let writeText: ReturnType<typeof vi.fn>;

describe('ReportBug', () => {
  beforeEach(() => {
    writeText = vi.fn();
    Object.defineProperty(Object.getPrototypeOf(navigator), 'clipboard', {
      configurable: true,
      get: () => ({ writeText }),
    });
  });

  it('renders prefilled report context from query params', () => {
    render(
      <MemoryRouter
        initialEntries={[
          '/report-bug?gameLink=abc123&gameName=Forest+Battle&gameStatus=preparation&username=tester',
        ]}
      >
        <ReportBug />
      </MemoryRouter>,
    );

    expect(screen.getByRole('heading', { name: /Report a bug/i })).toBeInTheDocument();
    expect(screen.getByText('abc123')).toBeInTheDocument();
    expect(screen.getByText('Forest Battle')).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Game link: abc123/)).toBeInTheDocument();
    expect(screen.getByDisplayValue(/Username: tester/)).toBeInTheDocument();
  });

  it('copies the generated report and reports clipboard failures', async () => {
    writeText.mockResolvedValue();
    render(
      <MemoryRouter initialEntries={['/report-bug?gameLink=abc123']}>
        <ReportBug />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /copy report/i }));
    expect(writeText).toHaveBeenCalledWith(
      expect.stringContaining('Game link: abc123'),
    );
    expect(await screen.findByRole('button', { name: 'Copied!' })).toBeInTheDocument();
  });

  it('shows a failure message when clipboard access is denied', async () => {
    writeText.mockRejectedValue(new Error('denied'));
    render(
      <MemoryRouter>
        <ReportBug />
      </MemoryRouter>,
    );

    fireEvent.click(screen.getByRole('button', { name: /copy report/i }));
    expect(await screen.findByRole('button', { name: 'Copy failed' })).toBeInTheDocument();
  });
});
