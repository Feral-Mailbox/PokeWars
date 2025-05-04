import { useAuth } from '../state/auth';

const Homepage = () => {
  const { user } = useAuth();

  return (
    <div className="pt-20">
      {user ? (
        <h1 className="text-3xl font-bold text-white">Success! You are logged in 🎉</h1>
      ) : (
        <h1 className="text-3xl font-bold text-white">Welcome! Please login to continue.</h1>
      )}
    </div>
  );
};

export default Homepage;
