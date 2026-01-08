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

// API base:
// - Default: same-origin `/api` (works for the single Render Docker service).
// - Override for split deployments (Render Static Site + separate backend):
//   set `VITE_API_BASE` to something like `https://YOUR-BACKEND.onrender.com/api`
const apiBase = (import.meta.env.VITE_API_BASE ?? "/api").replace(/\/$/, "");

async function readError(res: Response): Promise<string> {
  const status = `HTTP ${res.status}`;
  try {
    const data = await res.json();
    if (typeof data?.detail === "string") return `${status}: ${data.detail}`;
    if (typeof data?.message === "string") return `${status}: ${data.message}`;
    return `${status}: ${JSON.stringify(data)}`;
  } catch {
    try {
      const text = await res.text();
      const snippet = text.length > 200 ? `${text.slice(0, 200)}…` : text;
      return `${status}: ${snippet || "Unknown error"}`;
    } catch {
      return `${status}: Unknown error`;
    }
  }
}

const today = () => new Date().toISOString().slice(0, 10);

export default function App() {
  const [view, setView] = useState<"landing" | "group" | "pick" | "results">(
    "landing"
  );
  const [displayName, setDisplayName] = useState("");
  const [newGroupName, setNewGroupName] = useState("");
  const [joinCode, setJoinCode] = useState("");
  const [groupSearchQuery, setGroupSearchQuery] = useState("");
  const [groupSearchResults, setGroupSearchResults] = useState<Group[]>([]);
  const [groupSearchLoading, setGroupSearchLoading] = useState(false);
  const [selectedGroupForJoin, setSelectedGroupForJoin] = useState<Group | null>(null);
  const [groupSearchFocused, setGroupSearchFocused] = useState(false);
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
    try {
      const raw = localStorage.getItem("btl_session");
      return raw ? JSON.parse(raw) : null;
    } catch {
      try {
        localStorage.removeItem("btl_session");
      } catch {
        // ignore
      }
      return null;
    }
  }, []);

  useEffect(() => {
    if (stored?.group && stored?.user) {
      setGroup(stored.group);
      setUser(stored.user);
      setView("group");
    }
  }, [stored]);

  // Prevent "blank screen" states where view expects a group but none is loaded.
  useEffect(() => {
    if (!group && view !== "landing") {
      setView("landing");
    }
  }, [group, view]);

  useEffect(() => {
    if (!group || view !== "group") return;

    let cancelled = false;
    const controller = new AbortController();

    const fetchMembers = async () => {
      try {
        const res = await fetch(`${apiBase}/groups/${group.code}/members`, {
          signal: controller.signal
        });
        if (!res.ok) return;
        const data = await res.json();
        if (!cancelled) setMembers(Array.isArray(data) ? data : []);
      } catch {
        // ignore
      }
    };

    fetchMembers();
    const interval = window.setInterval(fetchMembers, 10_000);
    return () => {
      cancelled = true;
      controller.abort();
      window.clearInterval(interval);
    };
  }, [group, view]);

  useEffect(() => {
    const q = groupSearchQuery.trim();
    if (q.length < 1) {
      setGroupSearchResults([]);
      setGroupSearchLoading(false);
      return;
    }

    setGroupSearchLoading(true);
    const controller = new AbortController();
    const timeout = window.setTimeout(async () => {
      try {
        const url = `${apiBase}/groups/search?query=${encodeURIComponent(q)}&limit=10`;
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) {
          setGroupSearchResults([]);
          setGroupSearchLoading(false);
          return;
        }
        const data = await res.json();
        setGroupSearchResults(Array.isArray(data) ? data : []);
      } catch {
        setGroupSearchResults([]);
      } finally {
        setGroupSearchLoading(false);
      }
    }, 350);

    return () => {
      controller.abort();
      window.clearTimeout(timeout);
    };
  }, [groupSearchQuery]);

  const selectGroupForJoin = (g: Group) => {
    setSelectedGroupForJoin(g);
    setJoinCode(g.code);
    setGroupSearchQuery(g.name);
    setGroupSearchFocused(false);
  };

  useEffect(() => {
    if (!group) return;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${apiBase}/groups/${group.code}/picks?date=${selectedDate}`, {
          signal: controller.signal
        });
        if (!res.ok) {
          if (res.status === 404) {
            setError("This group no longer exists. Please create or join a group again.");
            localStorage.removeItem("btl_session");
            setGroup(null);
            setUser(null);
            setMembers([]);
            setPicks([]);
            setView("landing");
          } else {
            setPicks([]);
          }
          return;
        }
        const data = await res.json();
        setPicks(Array.isArray(data) ? data : []);
      } catch {
        setPicks([]);
      }
    })();
    return () => controller.abort();
  }, [group, selectedDate]);

  useEffect(() => {
    if (!group) return;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${apiBase}/groups/${group.code}/leaderboard?date=${selectedDate}`, {
          signal: controller.signal
        });
        if (!res.ok) {
          setLeaderboard([]);
          return;
        }
        const data = await res.json();
        setLeaderboard(Array.isArray(data) ? data : []);
      } catch {
        setLeaderboard([]);
      }
    })();
    return () => controller.abort();
  }, [group, selectedDate]);

  useEffect(() => {
    if (!group) return;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${apiBase}/groups/${group.code}/leaderboard/alltime`, {
          signal: controller.signal
        });
        if (!res.ok) {
          setAllTimeLeaderboard([]);
          return;
        }
        const data = await res.json();
        setAllTimeLeaderboard(Array.isArray(data) ? data : []);
      } catch {
        setAllTimeLeaderboard([]);
      }
    })();
    return () => controller.abort();
  }, [group]);

  useEffect(() => {
    if (view !== "pick") return;
    const controller = new AbortController();
    (async () => {
      try {
        const res = await fetch(`${apiBase}/nba/games?date=${selectedDate}`, {
          signal: controller.signal
        });
        if (!res.ok) {
          setGames([]);
          return;
        }
        const data = await res.json();
        setGames(Array.isArray(data) ? data : []);
      } catch {
        setGames([]);
      }
    })();
    return () => controller.abort();
  }, [selectedDate, view]);

  useEffect(() => {
    if (view !== "pick") return;
    const controller = new AbortController();
    (async () => {
      try {
        const url = `${apiBase}/nba/players?date=${selectedDate}&query=${playerQuery}`;
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) {
          setPlayers([]);
          return;
        }
        const data = await res.json();
        setPlayers(Array.isArray(data) ? data : []);
      } catch {
        setPlayers([]);
      }
    })();
    return () => controller.abort();
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
      body: JSON.stringify({ group_name: newGroupName, display_name: displayName })
    });
    if (!res.ok) {
      setError(await readError(res));
      return;
    }
    const data = await res.json();
    persistSession(data.group, data.user);
    setView("group");
  };

  const joinGroup = async () => {
    setError(null);
    const code = (selectedGroupForJoin?.code ?? joinCode).trim();
    const res = await fetch(`${apiBase}/groups/join`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ group_code: code, display_name: displayName })
    });
    if (!res.ok) {
      setError(await readError(res));
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
      setError(await readError(res));
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
      setError(await readError(res));
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
          <div className="grid" style={{ gridTemplateColumns: "1fr", gap: 16 }}>
            <div>
              <h3>Create a new group</h3>
              <label>
                Group Name
                <input
                  value={newGroupName}
                  onChange={(e) => setNewGroupName(e.target.value)}
                  placeholder="e.g. The Dawgs"
                />
              </label>
              <div className="actions">
                <button onClick={createGroup} disabled={!displayName || !newGroupName}>
                  Create Group
                </button>
              </div>
            </div>

            <div>
              <h3>Join an existing group</h3>
              <label>
                Search groups (name or code)
                <div className="autocomplete">
                  <input
                    value={groupSearchQuery}
                    onChange={(e) => {
                      setGroupSearchQuery(e.target.value);
                      setSelectedGroupForJoin(null);
                    }}
                    onFocus={() => setGroupSearchFocused(true)}
                    onBlur={() => window.setTimeout(() => setGroupSearchFocused(false), 150)}
                    placeholder="Start typing…"
                  />

                  {groupSearchFocused && groupSearchQuery.trim().length >= 1 && (
                    <div className="autocomplete-dropdown">
                      {groupSearchLoading ? (
                        <div className="autocomplete-item muted">Searching…</div>
                      ) : groupSearchResults.length === 0 ? (
                        <div className="autocomplete-item muted">No results.</div>
                      ) : (
                        groupSearchResults.map((g) => (
                          <button
                            key={g.id}
                            type="button"
                            className={
                              selectedGroupForJoin?.code === g.code
                                ? "autocomplete-item selected"
                                : "autocomplete-item"
                            }
                            onMouseDown={(e) => {
                              // Prevent input blur before we can select.
                              e.preventDefault();
                              selectGroupForJoin(g);
                            }}
                          >
                            <strong>{g.name}</strong> — <span className="code">{g.code}</span>
                          </button>
                        ))
                      )}
                    </div>
                  )}
                </div>
              </label>

              <label>
                Or enter code directly
                <input
                  value={joinCode}
                  onChange={(e) => {
                    setJoinCode(e.target.value);
                    setSelectedGroupForJoin(null);
                  }}
                  placeholder="ABC123"
                />
              </label>

              <div className="actions">
                <button
                  onClick={joinGroup}
                  disabled={!displayName || !(selectedGroupForJoin?.code || joinCode.trim())}
                >
                  Join Group
                </button>
              </div>
            </div>
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
