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

type PlayerProjection = {
  player_id: number;
  player_name: string;
  date: string;
  game_id?: string | null;
  source: string;
  last_updated: string;
  recent_games?: {
    n_games_used: number;
    points: number;
    assists: number;
    rebounds: number;
    steals: number;
    blocks: number;
    turnovers: number;
    personal_fouls: number;
  } | null;
  sportsbook?: {
    provider: string;
    last_updated: string;
    lines: Record<string, number>;
  } | null;
};

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
  const [selectedGameId, setSelectedGameId] = useState<string | null>(null);
  const [gamePlayers, setGamePlayers] = useState<Player[]>([]);
  const [playersLoading, setPlayersLoading] = useState(false);
  const [playerQuery, setPlayerQuery] = useState("");
  const [selectedPlayer, setSelectedPlayer] = useState<Player | null>(null);
  const [projection, setProjection] = useState<PlayerProjection | null>(null);
  const [projectionLoading, setProjectionLoading] = useState(false);
  const [leaderboard, setLeaderboard] = useState<LeaderboardRow[]>([]);
  const [allTimeLeaderboard, setAllTimeLeaderboard] = useState<LeaderboardRow[]>(
    []
  );
  const [pickResults, setPickResults] = useState<PickResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [apiReachable, setApiReachable] = useState<boolean | null>(null);
  const [apiBaseError, setApiBaseError] = useState<string | null>(null);

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

  const resetStaleSession = (message: string) => {
    try {
      localStorage.removeItem("btl_session");
    } catch {
      // ignore
    }
    setGroup(null);
    setUser(null);
    setMembers([]);
    setPicks([]);
    setLeaderboard([]);
    setAllTimeLeaderboard([]);
    setPickResults([]);
    setGroupSearchResults([]);
    setSelectedGroupForJoin(null);
    setJoinCode("");
    setGroupSearchQuery("");
    setView("landing");
    setError(message);
  };

  const handleGroupScopedNotFound = async (res: Response) => {
    // Prefer checking backend's explicit message.
    let detail: string | null = null;
    try {
      const contentType = res.headers.get("content-type") ?? "";
      if (contentType.includes("application/json")) {
        const data = await res.json();
        if (typeof data?.detail === "string") detail = data.detail;
      }
    } catch {
      // ignore
    }

    if (detail && detail.toLowerCase().includes("group not found")) {
      resetStaleSession(
        "Your saved session is stale (that group no longer exists). Please create or join a group again."
      );
      return;
    }

    // If the API health check is succeeding, a 404 on group routes is effectively a stale/invalid session.
    // Clearing it prevents the app from getting stuck in a broken state.
    if (apiReachable === true) {
      resetStaleSession("That group can't be found. Please create or join a group again.");
      return;
    }

    // Otherwise, treat it as an API base / routing issue (common with Static Site deployments).
    setApiReachable(false);
    setApiBaseError(
      `API requests are failing at "${apiBase}". If you deployed frontend and backend separately, set VITE_API_BASE=https://<backend-host>/api and redeploy the frontend.`
    );
  };

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

  // Detect misconfigured API base early (common when deploying frontend as a Static Site).
  useEffect(() => {
    const controller = new AbortController();
    setApiReachable(null);
    setApiBaseError(null);

    (async () => {
      try {
        const res = await fetch(`${apiBase}/healthz`, { signal: controller.signal });
        if (res.ok) {
          setApiReachable(true);
          setApiBaseError(null);
          return;
        }
        setApiReachable(false);
        setApiBaseError(
          `API health check failed at "${apiBase}/healthz" (HTTP ${res.status}). If you deployed frontend and backend separately, set VITE_API_BASE=https://<backend-host>/api and redeploy the frontend.`
        );
      } catch {
        setApiReachable(false);
        setApiBaseError(
          `API is unreachable at "${apiBase}/healthz". If you deployed frontend and backend separately, set VITE_API_BASE=https://<backend-host>/api and redeploy the frontend.`
        );
      }
    })();

    return () => controller.abort();
  }, [apiBase]);

  useEffect(() => {
    if (!group || view !== "group") return;

    let cancelled = false;
    const controller = new AbortController();

    const fetchMembers = async () => {
      try {
        const res = await fetch(`${apiBase}/groups/${group.code}/members`, {
          signal: controller.signal
        });
        if (!res.ok) {
          if (res.status === 404) await handleGroupScopedNotFound(res);
          return;
        }
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
          if (res.status === 404) await handleGroupScopedNotFound(res);
          setPicks([]);
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
          if (res.status === 404) await handleGroupScopedNotFound(res);
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
          if (res.status === 404) await handleGroupScopedNotFound(res);
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
    // Reset game/player state when the date changes.
    setSelectedGameId(null);
    setGamePlayers([]);
    setSelectedPlayer(null);
    setProjection(null);
    setPlayerQuery("");
  }, [selectedDate, view]);

  useEffect(() => {
    if (view !== "pick" || !selectedGameId) return;
    const controller = new AbortController();
    setPlayersLoading(true);
    setGamePlayers([]);
    setSelectedPlayer(null);
    setProjection(null);

    (async () => {
      try {
        const res = await fetch(`${apiBase}/nba/games/${selectedGameId}/players`, {
          signal: controller.signal
        });
        if (!res.ok) {
          setGamePlayers([]);
          return;
        }
        const data = await res.json();
        setGamePlayers(Array.isArray(data) ? data : []);
      } catch {
        setGamePlayers([]);
      } finally {
        setPlayersLoading(false);
      }
    })();

    return () => controller.abort();
  }, [selectedGameId, view]);

  useEffect(() => {
    if (view !== "pick" || !selectedPlayer) return;
    const controller = new AbortController();
    setProjectionLoading(true);
    setProjection(null);

    (async () => {
      try {
        const url = `${apiBase}/nba/players/${selectedPlayer.player_id}/projection?date=${selectedDate}&game_id=${encodeURIComponent(
          selectedPlayer.game_id
        )}`;
        const res = await fetch(url, { signal: controller.signal });
        if (!res.ok) {
          setProjection(null);
          return;
        }
        const data = await res.json();
        setProjection(data && typeof data === "object" ? data : null);
      } catch {
        setProjection(null);
      } finally {
        setProjectionLoading(false);
      }
    })();

    return () => controller.abort();
  }, [selectedPlayer, selectedDate, view]);

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
      if (res.status === 404) {
        await handleGroupScopedNotFound(res);
        return;
      }
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
      if (res.status === 404) {
        await handleGroupScopedNotFound(res);
        return;
      }
      setError(await readError(res));
      return;
    }
    const data = await res.json();
    setLeaderboard(Array.isArray(data?.leaderboard) ? data.leaderboard : []);
    setPickResults(Array.isArray(data?.picks_with_results) ? data.picks_with_results : []);
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

      {apiBaseError && <div className="error">{apiBaseError}</div>}
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
                        (Array.isArray(groupSearchResults) ? groupSearchResults : []).map((g) => (
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
              {(Array.isArray(members) ? members : []).map((member) => (
                <li key={member.id}>{member.display_name}</li>
              ))}
            </ul>
          </div>
          <div className="card">
            <h3>Today’s Picks</h3>
            {(Array.isArray(picks) ? picks : []).length === 0 ? (
              <p>No picks yet for this date.</p>
            ) : (
              <ul className="list">
                {(Array.isArray(picks) ? picks : []).map((pick) => (
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
            <h2>Schedule</h2>
            <label>
              Pick Date
              <input
                type="date"
                value={selectedDate}
                onChange={(e) => setSelectedDate(e.target.value)}
              />
            </label>
            <div className="games">
              <h3>Today’s Games</h3>
              <ul>
                {(Array.isArray(games) ? games : []).map((game) => (
                  <li key={game.game_id}>
                    <button
                      className={selectedGameId === game.game_id ? "selected" : ""}
                      onClick={() => setSelectedGameId(game.game_id)}
                      type="button"
                    >
                      {game.away_team} @ {game.home_team} — {game.start_time}
                    </button>
                  </li>
                ))}
              </ul>
            </div>
          </div>
          <div className="card">
            <h3>Game Players</h3>
            {!selectedGameId ? (
              <p>Select a game to view players.</p>
            ) : (
              <>
                <input
                  placeholder="Filter players"
                  value={playerQuery}
                  onChange={(e) => setPlayerQuery(e.target.value)}
                />

                {playersLoading ? (
                  <p>Loading players…</p>
                ) : (
                  <ul className="list">
                    {(Array.isArray(gamePlayers) ? gamePlayers : [])
                      .filter((p) =>
                        playerQuery.trim()
                          ? p.player_name.toLowerCase().includes(playerQuery.toLowerCase())
                          : true
                      )
                      .map((player) => (
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
                )}

                <div style={{ marginTop: "1rem" }}>
                  <h3>Projected Stats</h3>
                  {!selectedPlayer ? (
                    <p>Select a player to see projections.</p>
                  ) : projectionLoading ? (
                    <p>Loading projection…</p>
                  ) : !projection ? (
                    <p>No projection available.</p>
                  ) : (
                    <div className="breakdown">
                      <p style={{ marginTop: 0 }}>
                        <strong>{projection.player_name}</strong> —{" "}
                        {projection.source === "sportsbook_provider"
                          ? "Sportsbook line"
                          : "Recent-games projection"}
                      </p>

                      {projection.sportsbook?.lines &&
                        Object.keys(projection.sportsbook.lines).length > 0 && (
                          <>
                            <h4>Sportsbook lines</h4>
                            <ul className="list">
                              {Object.entries(projection.sportsbook.lines).map(([k, v]) => (
                                <li key={k}>
                                  <strong>{k.toUpperCase()}</strong>: {v}
                                </li>
                              ))}
                            </ul>
                          </>
                        )}

                      {projection.recent_games && (
                        <>
                          <h4>Recent-games projection</h4>
                          <table>
                            <thead>
                              <tr>
                                <th>Stat</th>
                                <th>Projected</th>
                              </tr>
                            </thead>
                            <tbody>
                              {(
                                [
                                  ["points", projection.recent_games.points],
                                  ["assists", projection.recent_games.assists],
                                  ["rebounds", projection.recent_games.rebounds],
                                  ["steals", projection.recent_games.steals],
                                  ["blocks", projection.recent_games.blocks],
                                  ["turnovers", projection.recent_games.turnovers],
                                  ["personal_fouls", projection.recent_games.personal_fouls]
                                ] as const
                              ).map(([stat, value]) => (
                                <tr key={stat}>
                                  <td>{stat}</td>
                                  <td>{value.toFixed(1)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                          <p style={{ marginBottom: 0, color: "#64748b" }}>
                            Based on last {projection.recent_games.n_games_used} games.
                          </p>
                        </>
                      )}
                    </div>
                  )}
                </div>
              </>
            )}
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
            {(Array.isArray(leaderboard) ? leaderboard : []).length === 0 ? (
              <p>No scores yet.</p>
            ) : (
              <ol>
                {(Array.isArray(leaderboard) ? leaderboard : []).map((row) => (
                  <li key={row.user_id}>
                    {row.user_name}: {row.score.toFixed(1)}
                  </li>
                ))}
              </ol>
            )}
            <h3>All-Time</h3>
            {(Array.isArray(allTimeLeaderboard) ? allTimeLeaderboard : []).length === 0 ? (
              <p>No all-time scores yet.</p>
            ) : (
              <ol>
                {(Array.isArray(allTimeLeaderboard) ? allTimeLeaderboard : []).map((row) => (
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
            {(Array.isArray(pickResults) ? pickResults : []).length === 0 ? (
              <p>No pick results yet.</p>
            ) : (
              (Array.isArray(pickResults) ? pickResults : []).map((result) => (
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
                      {Object.keys(result.breakdown.expected ?? {}).map((stat) => (
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
