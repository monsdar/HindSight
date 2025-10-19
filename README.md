# HoopTipp - Flexible Prediction Platform

**HoopTipp** is a self-hosted, extensible prediction platform. While it started as a family-friendly NBA prediction app, it has evolved into a **general-purpose prediction system** that can track any type of predictable event.

Predict NBA games, elections, Olympic outcomes, personal goals, or create your own custom prediction events!

---

## What Makes HoopTipp Special

### Universal Prediction System
- **Any Event Type**: Sports, politics, personal goals, world events
- **Extensible Sources**: Automatic imports from external APIs
- **Beautiful UI**: Clean, modern interface with Tailwind CSS
- **Family-Friendly**: Simple user activation without complex authentication
- **Smart Scoring**: Configurable points, lock bonuses, and leaderboards

### Built-in NBA Support
HoopTipp comes with full NBA integration:
- Automatic game imports from BallDontLie API
- 30 NBA teams and active player database
- Weekly game predictions
- Custom season events (MVP, All-Stars, etc.)

---

## Core Concepts

### Prediction Events
Any binary outcome you want to predict:
- **Active Timeframe**: Events have opening times and deadlines
- **Multiple Options**: Choose from teams, players, countries, or custom choices
- **Point Values**: Configurable scoring for each event type
- **Lock System**: Commit to high-confidence picks for bonus points

### Event Sources
Automatic prediction importers:
- **NBA Source**: Imports upcoming games automatically
- **Manual Events**: Create any custom prediction via admin
- **Custom Sources**: Easy to add new integrations (see `docs/generic_prediction_system_design.md`)

### Option Categories
Flexible organization system:
- **NBA Teams**: All 30 teams with metadata
- **NBA Players**: Active players with team/position info
- **Countries**: For international predictions
- **Custom Categories**: Create any category you need

---

## Example Use Cases

### Sports Predictions
- NBA games, standings, awards
- Olympic medal counts
- Tournament winners

### Political Predictions
- Election results
- Cabinet appointments
- Policy outcomes

### World Events
- "Which country names the next Pope?"
- "Which country wins 30+ Olympic medals first?"
- Climate milestone predictions

### Personal Tracking
- "Will I bike to work 10+ times this month?"
- Habit formation goals
- Personal achievement predictions

---

## Getting Started

### Prerequisites
- Python 3.12+
- PostgreSQL (or SQLite for development)
- Optional: BallDontLie API token for NBA features

### Local Setup

1. **Install dependencies:**
   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Set up the database:**
   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

3. **Configure NBA integration (optional):**
   ```bash
   export BALLDONTLIE_API_TOKEN=your_api_token_here
   ```

4. **Run tests:**
   ```bash
   python manage.py test
   ```

5. **Start the server:**
   ```bash
   python manage.py runserver
   ```

6. **Access the app:**
   - Homepage: http://localhost:8000
   - Admin panel: http://localhost:8000/admin

### First Steps

1. **Create Users** (via `/admin`):
   - Go to the admin panel
   - Add users who will make predictions
   - No complex authentication needed!

2. **Sync NBA Data** (optional):
   - In admin, go to "NBA Teams" and click "Sync Teams"
   - Go to "NBA Players" and click "Sync Players"
   - This imports all teams and active players

3. **Import Games**:
   - NBA games are automatically synced when you visit the homepage
   - Or manually trigger sync in admin under "Event Sources"

4. **Make Predictions**:
   - On the homepage, select a user
   - View upcoming events and make your picks
   - Optionally "lock" picks you're confident in
   - Save and switch users!

---

## How Predictions Work

### User Activation Model
Simple, family-friendly approach:
1. **No authentication required** on the main page
2. Select a user from the dropdown
3. Make predictions
4. "Finish Round" to clear selection
5. Next user can then select themselves

### Lock System
- Each user has a limited number of "locks" (default: 1)
- Locked picks multiply points if correct
- Locks return after the event deadline
- Forfeited locks return after a penalty period

### Scoring
- **Base Points**: Configurable per event type
- **Lock Multiplier**: 2x or 3x for locked picks
- **Bonus Events**: Special high-value predictions
- **Leaderboard**: Real-time standings with detailed breakdowns

---

## Production Deployment

HoopTipp is designed for Railway deployment:

1. **Environment Variables:**
   ```bash
   BALLDONTLIE_API_TOKEN=your_token
   DATABASE_URL=postgresql://...
   SECRET_KEY=your_secret_key
   ALLOWED_HOSTS=yourdomain.com
   CSRF_TRUSTED_ORIGINS=https://yourdomain.com
   ```

2. **Deploy to Railway:**
   - Connect your repository
   - Set environment variables
   - Deploy!

The included `Dockerfile` and `docker-entrypoint.sh` handle the setup automatically.

---

## License

See [LICENSE](LICENSE) file for details.
