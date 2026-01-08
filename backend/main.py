from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import uvicorn

# Initialize FastAPI app
app = FastAPI(
    title="NBA API",
    description="A FastAPI application for NBA data and analytics",
    version="1.0.0"
)

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic Models
class Player(BaseModel):
    id: int
    name: str
    team: str
    position: str
    number: int


class Team(BaseModel):
    id: int
    name: str
    city: str
    conference: str
    wins: int
    losses: int


class Game(BaseModel):
    id: int
    date: str
    home_team: str
    away_team: str
    home_score: int
    away_score: int


# In-memory data storage (replace with database in production)
players_db: List[Player] = []
teams_db: List[Team] = []
games_db: List[Game] = []


# Health check endpoint
@app.get("/health")
async def health_check():
    """Check if the API is running"""
    return {"status": "healthy", "message": "NBA API is running"}


# Player Endpoints
@app.get("/players", response_model=List[Player])
async def get_players():
    """Get all players"""
    return players_db


@app.get("/players/{player_id}", response_model=Player)
async def get_player(player_id: int):
    """Get a specific player by ID"""
    for player in players_db:
        if player.id == player_id:
            return player
    raise HTTPException(status_code=404, detail="Player not found")


@app.post("/players", response_model=Player)
async def create_player(player: Player):
    """Create a new player"""
    players_db.append(player)
    return player


@app.put("/players/{player_id}", response_model=Player)
async def update_player(player_id: int, player: Player):
    """Update a player"""
    for i, p in enumerate(players_db):
        if p.id == player_id:
            players_db[i] = player
            return player
    raise HTTPException(status_code=404, detail="Player not found")


@app.delete("/players/{player_id}")
async def delete_player(player_id: int):
    """Delete a player"""
    for i, p in enumerate(players_db):
        if p.id == player_id:
            players_db.pop(i)
            return {"message": "Player deleted successfully"}
    raise HTTPException(status_code=404, detail="Player not found")


# Team Endpoints
@app.get("/teams", response_model=List[Team])
async def get_teams():
    """Get all teams"""
    return teams_db


@app.get("/teams/{team_id}", response_model=Team)
async def get_team(team_id: int):
    """Get a specific team by ID"""
    for team in teams_db:
        if team.id == team_id:
            return team
    raise HTTPException(status_code=404, detail="Team not found")


@app.post("/teams", response_model=Team)
async def create_team(team: Team):
    """Create a new team"""
    teams_db.append(team)
    return team


@app.put("/teams/{team_id}", response_model=Team)
async def update_team(team_id: int, team: Team):
    """Update a team"""
    for i, t in enumerate(teams_db):
        if t.id == team_id:
            teams_db[i] = team
            return team
    raise HTTPException(status_code=404, detail="Team not found")


@app.delete("/teams/{team_id}")
async def delete_team(team_id: int):
    """Delete a team"""
    for i, t in enumerate(teams_db):
        if t.id == team_id:
            teams_db.pop(i)
            return {"message": "Team deleted successfully"}
    raise HTTPException(status_code=404, detail="Team not found")


# Game Endpoints
@app.get("/games", response_model=List[Game])
async def get_games():
    """Get all games"""
    return games_db


@app.get("/games/{game_id}", response_model=Game)
async def get_game(game_id: int):
    """Get a specific game by ID"""
    for game in games_db:
        if game.id == game_id:
            return game
    raise HTTPException(status_code=404, detail="Game not found")


@app.post("/games", response_model=Game)
async def create_game(game: Game):
    """Create a new game"""
    games_db.append(game)
    return game


@app.put("/games/{game_id}", response_model=Game)
async def update_game(game_id: int, game: Game):
    """Update a game"""
    for i, g in enumerate(games_db):
        if g.id == game_id:
            games_db[i] = game
            return game
    raise HTTPException(status_code=404, detail="Game not found")


@app.delete("/games/{game_id}")
async def delete_game(game_id: int):
    """Delete a game"""
    for i, g in enumerate(games_db):
        if g.id == game_id:
            games_db.pop(i)
            return {"message": "Game deleted successfully"}
    raise HTTPException(status_code=404, detail="Game not found")


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "message": "Welcome to NBA API",
        "version": "1.0.0",
        "docs": "/docs",
        "redoc": "/redoc"
    }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
