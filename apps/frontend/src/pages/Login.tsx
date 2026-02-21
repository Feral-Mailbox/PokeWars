import { useAuth } from '../state/auth';
import { useEffect } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

const Login = () => {
  const { user } = useAuth();
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();
  const nextPath = searchParams.get('next') || '/';

  // If user is already logged in, redirect to the next path
  useEffect(() => {
    if (user) {
      navigate(nextPath);
    }
  }, [user, navigate, nextPath]);

  return (
    <div className="pt-20">
      <h1 className="text-3xl font-bold text-white">Welcome! Please login to continue.</h1>
      <p className="text-gray-400 mt-4">Use the login form in the navbar at the top.</p>
    </div>
  );
};

export default Login;
