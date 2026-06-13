import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { MemoryRouter } from 'react-router-dom';
import ReportBug from '@/pages/ReportBug';

describe('ReportBug', () => {
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
});
