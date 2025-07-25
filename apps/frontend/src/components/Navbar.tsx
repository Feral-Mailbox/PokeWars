import { useState, useEffect, useRef } from 'react';
import { useAuth } from '../state/auth';
import { useNavigate } from 'react-router-dom';
import { secureFetch } from '@/utils/secureFetch';
import logo from '../assets/react.svg';

const Navbar = () => {
  const [user, setUser] = useState<User | null>(null);
  const [showDropdown, setShowDropdown] = useState(false);
  const [isRegister, setIsRegister] = useState(false);
  const [showGamesMenu, setShowGamesMenu] = useState(false);
  const [gamesLocked, setGamesLocked] = useState(false);
  const gamesRef = useRef<HTMLDivElement>(null);
  const loginRef = useRef<HTMLDivElement>(null);
  const navigate = useNavigate();

  type User = {
    id: number;
    username: string;
    email: string;
    avatar: string;
    elo: number;
    currency: number;
  };

  const [form, setForm] = useState({
    username: '',
    password: '',
    email: '',
    confirm: '',
  });

  useEffect(() => {
    const checkSession = async () => {
      try {
        const res = await secureFetch<User>('/api/me');
        if (res?.ok) {
          const data = await res.json();
          setUser(data);
        }
      } catch (err) {
        console.error('Session check failed', err);
      }
    };
    checkSession();
  }, [setUser]);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (gamesRef.current && !gamesRef.current.contains(event.target as Node)) {
        setShowGamesMenu(false);
        setGamesLocked(false);
      }
      if (loginRef.current && !loginRef.current.contains(event.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (isRegister && form.password !== form.confirm) {
      alert('Passwords do not match');
      return;
    }

    const endpoint = isRegister ? '/api/register' : '/api/login';
    const payload = isRegister
      ? { username: form.username, password: form.password, email: form.email }
      : { username: form.username, password: form.password };

    const res = await secureFetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });

    if (res?.ok) {
      const data = await res.json();
      setUser(data);
      setShowDropdown(false);
    } else {
      alert(isRegister ? 'Registration failed' : 'Login failed');
    }
  };

  const handleLogout = async () => {
    await secureFetch('/api/logout', {
      method: 'POST',
    });
    logout();
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setForm({ ...form, [e.target.name]: e.target.value });
  };

  return (
    <nav className="h-16 flex flex-row justify-between items-center px-4 bg-gray-900 text-white fixed top-0 left-0 w-full z-10 shadow-md">
      <button onClick={() => navigate('/')}>
        <img
          src={logo}
          alt="logo"
          className="w-8 h-8 transition-transform duration-1000 hover:rotate-[360deg]"
        />
      </button>

      <div className="flex flex-row items-center gap-4 relative">
        {/* Games dropdown */}
        <div
          ref={gamesRef}
          className="relative"
          onMouseEnter={() => {
            if (!gamesLocked) setShowGamesMenu(true);
          }}
          onMouseLeave={() => {
            if (!gamesLocked) setShowGamesMenu(false);
          }}
        >
          <button
            onClick={() => {
              setShowGamesMenu(true);
              setGamesLocked(true);
            }}
            className="text-sm px-2 py-1 rounded bg-transparent shadow-none hover:text-blue-400 transition-colors"
          >
            Games
          </button>
          {showGamesMenu && (
            <div className="absolute top-full mt-1 bg-gray-800 text-white rounded shadow-md w-48 z-20">
              <button
                onClick={() => {
                  navigate('/games/create');
                  setShowGamesMenu(false);
                  setGamesLocked(false);
                }}
                className="block w-full text-left px-4 py-2 hover:bg-gray-700"
              >
                Create Game
              </button>
              <button
                onClick={() => {
                  navigate('/games/join');
                  setShowGamesMenu(false);
                  setGamesLocked(false);
                }}
                className="block w-full text-left px-4 py-2 hover:bg-gray-700"
              >
                Join Game
              </button>
              <button
                onClick={() => {
                  navigate('/games/in-progress');
                  setShowGamesMenu(false);
                  setGamesLocked(false);
                }}
                className="block w-full text-left px-4 py-2 hover:bg-gray-700"
              >
                In-Progress
              </button>
              <button
                onClick={() => {
                  navigate('/games/completed');
                  setShowGamesMenu(false);
                  setGamesLocked(false);
                }}
                className="block w-full text-left px-4 py-2 hover:bg-gray-700"
              >
                Completed
              </button>
            </div>
          )}
        </div>

        {/* Auth controls */}
        {user ? (
          <>
            <span className="text-sm text-gray-300">Welcome, {user.username}</span>
            <button
              onClick={handleLogout}
              className="text-sm px-2 py-1 rounded bg-transparent shadow-none hover:text-blue-400 transition-colors"
            >
              Logout
            </button>
          </>
        ) : (
          <div ref={loginRef}>
            <button
              onClick={() => setShowDropdown(!showDropdown)}
              className="text-sm px-2 py-1 rounded bg-transparent shadow-none hover:text-blue-400 transition-colors"
            >
              {isRegister ? 'Register' : 'Login'}
            </button>

            {showDropdown && (
              <div className="absolute right-0 top-10 bg-gray-800 text-white p-4 rounded shadow-lg w-64 z-20">
                <form onSubmit={handleSubmit} className="flex flex-col gap-2">
                  <input
                    className="bg-gray-700 text-white px-2 py-1 rounded"
                    name="username"
                    placeholder="Username"
                    onChange={handleChange}
                    required
                  />
                  <input
                    className="bg-gray-700 text-white px-2 py-1 rounded"
                    type="password"
                    name="password"
                    placeholder="Password"
                    onChange={handleChange}
                    required
                  />
                  {isRegister && (
                    <>
                      <input
                        className="bg-gray-700 text-white px-2 py-1 rounded"
                        type="password"
                        name="confirm"
                        placeholder="Confirm Password"
                        onChange={handleChange}
                        required
                      />
                      <input
                        className="bg-gray-700 text-white px-2 py-1 rounded"
                        type="email"
                        name="email"
                        placeholder="Email"
                        onChange={handleChange}
                        required
                      />
                    </>
                  )}
                  <button type="submit" className="bg-blue-500 text-white py-1 rounded">
                    Submit
                  </button>
                </form>
                <button
                  onClick={() => setIsRegister(!isRegister)}
                  className="text-sm mt-2 text-blue-400 underline"
                >
                  {isRegister ? 'Back to Login' : 'Create Account'}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </nav>
  );
};

export default Navbar;
