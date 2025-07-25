import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import NotFound from '../../src/pages/NotFound';

describe('NotFound', () => {
  it('displays the 404 message and suggestion', () => {
    render(<NotFound />);
    expect(screen.getByText(/404 - Page Not Found/i)).toBeInTheDocument();
    expect(screen.getByText(/That route doesn't exist/i)).toBeInTheDocument();
  });
});
