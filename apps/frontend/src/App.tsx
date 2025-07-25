import { Routes, Route } from 'react-router-dom';
import { WebSocketProvider } from './state/WebSocketContext';
import Homepage from './pages/Homepage';
import NotFound from './pages/NotFound';
import Navbar from './components/Navbar';
import CreateGame from './pages/games/CreateGame';
import JoinGame from './pages/games/JoinGame';
import ActiveGames from './pages/games/ActiveGames';
import CompletedGames from './pages/games/CompletedGames';
import GamePage from './pages/games/GamePage';

function App() {
  return (
    <WebSocketProvider>
      <Navbar />
      <Routes>
        <Route path="/" element={<Homepage />} />
        <Route path="/games/create" element={<CreateGame />} />
        <Route path="/games/join" element={<JoinGame />} />
        <Route path="/games/in-progress" element={<ActiveGames />} />
        <Route path="/games/completed" element={<CompletedGames />} />
        <Route path="/games/:gameId" element={<GamePage />} />
        <Route path="*" element={<NotFound />} />
      </Routes>
    </WebSocketProvider>
  );
}

export default App;
