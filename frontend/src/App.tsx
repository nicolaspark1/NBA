import { useEffect, useMemo, useState } from "react";

type Group = { id: number; name: string; code: string };

type User = { id: number; display_name: string };

type Member = { id: number; display_name: string; joined_at: string };

type PickRow = {
  id: number;
  user_id: number;
  user_name: string;
  player_name: string;
  status: string;
};

type Game = {
  game_id: string;
  home_team: string;
  away_team: string;
  start_time: string;
};

type Player = {
  player_id: number;
  player_name: string;
  team: string;
  game_id: string;
};

type LeaderboardRow = { user_id: number; user_name: string; score: number };

type PickResult = {
  pick_id: number;
  score: number;
  breakdown: {
    expected: Record<string, number>;
    actual: Record<string, number>;
    contributions: Record<string, number>;
  };
};

// In dev, Vite proxies `/api` to the backend (see `vite.config.ts`).
// In production (Render Docker), the backend serves the built frontend and `/api` is same-origin.
const apiBase = "/api";

const today = () => new Date().toISOString().slice(0, 10);

export default function App() {
  const [view, setView] = useState<"landing" | "group" | "pick" | "results">(
    "landing"
  );
  const [displayName, setDisplayName] = useState("");
  const [groupCode, setGroupCode] = useState("");
  const [group, setGroup] = useState<Group | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [members, setMembers] = useState<Member[]>([]);
  const [selectedDate, setSelectedDate] = useState(today());
  const [picks, setPicks] = useState<PickRow[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [players, setPlayers] = useState<Player[]>([]);
  const [playerQuery, setPlayerQuery] = useState("");
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [allTimeLeaderboard, setAllTimeLeaderboard] = useState<LeaderboardRow[]>(
    []
  );
  const [pickResults, setPickResults] = useState<PickResult[]>([]);
  const [error, setError] = useState<string | null>(null);

  const stored = useMemo(() => {
    const raw = localStorage.getItem("btl_session");
    return raw ? JSON.parse(raw) : null;
  }, []);

  useEffect(() => {
    if (stored?.group && stored?.user) {
      setGroup(stored.group);
      setUser(stored.user);
      setView("group");
    }
  }, [stored]);

  useEffect(() => {
    if (!group) return;
    fetch(`${apiBase}/groups/${group.code}/members`)
      .then((res) => res.json())
      .then(setMembers)
      .catch(() => setMembers([]));
  }, [group]);

  useEffect(() => {
    if (!group) return;
    fetch(`${apiBase}/groups/${group.code}/picks?date=${selectedDate}`)
      .then((res) => res.json())
      .then(setPicks)
      .catch(() => setPicks([]));
  }, [group, selectedDate]);

  useEffect(() => {
    if (!group) return;
    fetch(`${apiBase}/groups/${group.code}/leaderboard?date=${selectedDate}`)
      .then((res) => res.json())
      .then(setLeaderboard)
      .catch(() => setLeaderboard([]));
  }, [group, selectedDate]);

  useEffect(() => {
    if (!group) return;
    fetch(`${apiBase}/groups/${group.code}/leaderboard/alltime`)
      .then((res) => res.json())
      .then(setAllTimeLeaderboard)
      .catch(() => setAllTimeLeaderboard([]));
  }, [group]);

  useEffect(() => {
    if (view !== "pick") return;
    fetch(`${apiBase}/nba/games?date=${selectedDate}`)
      .then((res) => res.json())
      .then(setGames)
      .catch(() => setGames([]));
  }, [selectedDate, view]);

  useEffect(() => {
    if (view !== "pick") return;
    const url = `${apiBase}/nba/players?date=${selectedDate}&query=${playerQuery}`;
    fetch(url)
      .then((res) => res.json())
      .then(setPlayers)
      .catch(() => setPlayers([]));
  }, [selectedDate, playerQuery, view]);

  const persistSession = (nextGroup: Group, nextUser: User) => {
    setGroup(nextGroup);
    setUser(nextUser);
    localStorage.setItem("btl_session", JSON.stringify({ group: nextGroup, user: nextUser }));
  };

  const createGroup = async () => {
    setError(null);
    const res = await fetch(`${apiBase}/groups`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_name: groupCode, display_name: displayName })
    });
    if (!res.ok) {
      setError("Unable to create group.");
      return;
    }
    const data = await res.json();
    persistSession(data.group, data.user);
    setView("group");
  };

  const joinGroup = async () => {
    setError(null);
    const res = await fetch(`${apiBase}/groups/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_code: groupCode, display_name: displayName })
    });
    if (!res.ok) {
      setError("Unable to join group.");
      return;
    }
    const data = await res.json();
    persistSession(data.group, data.user);
    setView("group");
  };

  const submitPick = async () => {
    if (!group || !user || !selectedPlayer) return;
    setError(null);
    const res = await fetch(`${apiBase}/groups/${group.code}/picks`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        user_id: user.id,
        date: selectedDate,
        player_id: selectedPlayer.player_id,
        player_name: selectedPlayer.player_name
      })
    });
    if (!res.ok) {
      const message = await res.json();
      setError(message.detail ?? "Unable to submit pick.");
      return;
    }
    setSelectedPlayer(null);
    setView("group");
  };

  const scoreDay = async () => {
    if (!group) return;
    setError(null);
    const res = await fetch(`${apiBase}/groups/${group.code}/score?date=${selectedDate}`, {
      method: "POST"
    });
    if (!res.ok) {
      setError("Unable to score day.");
      return;
    }
    const data = await res.json();
    setLeaderboard(data.leaderboard ?? []);
    setPickResults(data.picks_with_results ?? []);
    setView("results");
  };

  const resetSession = () => {
    localStorage.removeItem("btl_session");
    setGroup(null);
    setUser(null);
    setMembers([]);
    setPicks([]);
    setView("landing");
  };

  return (
    <div className="app">
      <header className="header">
        <div>
          <h1>Beat the Line</h1>
          <p>Pick one player, beat the expected line, climb the leaderboard.</p>
        </div>
        {group && (
          <div className="session">
            <span>{group.name}</span>
            <span className="code">Code: {group.code}</span>
            <button onClick={resetSession}>Reset</button>
          </div>
        )}
      </header>

      {error && <div className="error">{error}</div>}

      {view === "landing" && (
        <div className="card">
          <h2>Get Started</h2>
          <label>
            Display Name
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
          </label>
          <label>
            Group Name / Code
            <input value={groupCode} onChange={(e) => setGroupCode(e.target.value)} />
          </label>
          <div className="actions">
            <button onClick={createGroup} disabled={!displayName || !groupCode}>
              Create Group
            </button>
            <button onClick={joinGroup} disabled={!displayName || !groupCode}>
              Join Group
            </button>
          </div>
        </div>
      )}

      {view === "group" && group && (
        <div className="grid">
          <div className="card">
            <h2>Group Home</h2>
            <label>
              Pick Date
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
              />
            </label>
            <div className="actions">
              <button onClick={() => setView("pick")}>Make a Pick</button>
              <button onClick={scoreDay}>Score Day</button>
              <button onClick={() => setView("results")}>View Results</button>
            </div>
            <h3>Members</h3>
            <ul>
              {members.map((member) => (
                <li key={member.id}>{member.display_name}</li>
              ))}
            </ul>
          </div>
          <div className="card">
            <h3>Today’s Picks</h3>
            {picks.length === 0 ? (
              <p>No picks yet for this date.</p>
            ) : (
              <ul className="list">
                {picks.map((pick) => (
                  <li key={pick.id}>
                    <strong>{pick.user_name}</strong>: {pick.player_name} ({pick.status})
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}

      {view === "pick" && group && (
        <div className="grid">
          <div className="card">
            <h2>Make a Pick</h2>
            <label>
              Pick Date
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
              />
            </label>
            <div className="games">
              <h3>Games</h3>
              <ul>
                {games.map((game) => (
                  <li key={game.game_id}>
                    {game.away_team} @ {game.home_team} — {game.start_time}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="card">
            <h3>Search Players</h3>
            <input
              placeholder="Search player"
              value={playerQuery}
              onChange={(e) => setPlayerQuery(e.target.value)}
            />
            <ul className="list">
              {players.map((player) => (
                <li key={`${player.game_id}-${player.player_id}`}>
                  <button
                    className={
                      selectedPlayer?.player_id === player.player_id ? "selected" : ""
                    }
                    onClick={() => setSelectedPlayer(player)}
                  >
                    {player.player_name} ({player.team})
                  </button>
                </li>
              ))}
            </ul>
            <button
              onClick={submitPick}
              disabled={!selectedPlayer}
              className="primary"
            >
              Confirm Pick
            </button>
            <button onClick={() => setView("group")} className="secondary">
              Back
            </button>
          </div>
        </div>
      )}

      {view === "results" && group && (
        <div className="grid">
          <div className="card">
            <h2>Daily Leaderboard</h2>
            {leaderboard.length === 0 ? (
              <p>No scores yet.</p>
            ) : (
              <ol>
                {leaderboard.map((row) => (
                  <li key={row.user_id}>
                    {row.user_name}: {row.score.toFixed(1)}
                  </li>
                ))}
              </ol>
            )}
            <h3>All-Time</h3>
            {allTimeLeaderboard.length === 0 ? (
              <p>No all-time scores yet.</p>
            ) : (
              <ol>
                {allTimeLeaderboard.map((row) => (
                  <li key={row.user_id}>
                    {row.user_name}: {row.score.toFixed(1)}
                  </li>
                ))}
              </ol>
            )}
            <button onClick={() => setView("group")}>Back to Group</button>
          </div>
          <div className="card">
            <h2>Pick Breakdown</h2>
            {pickResults.length === 0 ? (
              <p>No pick results yet.</p>
            ) : (
              pickResults.map((result) => (
                <div key={result.pick_id} className="breakdown">
                  <h4>Pick #{result.pick_id} — Score {result.score.toFixed(1)}</h4>
                  <table>
                    <thead>
                      <tr>
                        <th>Stat</th>
                        <th>Expected</th>
                        <th>Actual</th>
                        <th>Contribution</th>
                      </tr>
                    </thead>
                    <tbody>
                      {Object.keys(result.breakdown.expected).map((stat) => (
                        <tr key={stat}>
                          <td>{stat}</td>
                          <td>{result.breakdown.expected[stat].toFixed(1)}</td>
                          <td>{result.breakdown.actual[stat]?.toFixed(1)}</td>
                          <td>{result.breakdown.contributions[stat].toFixed(2)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
