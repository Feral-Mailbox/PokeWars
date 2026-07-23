import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import App from '@/App';

describe('App Routing', () => {
  it('renders home route', async () => {
    render(
      <MemoryRouter initialEntries={['/']}>
        <App />
      </MemoryRouter>,
    );
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /PokéTactics/i })).toBeInTheDocument();
    });
    expect(screen.getByRole('button', { name: /Log in/i })).toBeInTheDocument();
  });

  it('renders create game route', () => {
    render(
      <MemoryRouter initialEntries={['/games/create']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Create Game/i)).toBeInTheDocument();
  });

  it('renders 404 for unknown route', () => {
    render(
      <MemoryRouter initialEntries={['/unknown']}>
        <App />
      </MemoryRouter>,
    );
    expect(screen.getByText(/Not Found/i)).toBeInTheDocument();
  });
});
