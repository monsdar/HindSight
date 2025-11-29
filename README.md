# HindSight - Flexible Prediction Platform

**HindSight** is a self-hosted, extensible prediction platform. While it started as a family-friendly NBA prediction app, it has evolved into a **general-purpose prediction system** that can track any type of predictable event.

Predict NBA games, elections, Olympic outcomes, personal goals, or create your own custom prediction events!

---

## What Makes HindSight Special

### Universal Prediction System
- **Any Event Type**: Sports, politics, personal goals, world events
- **Extensible Sources**: Automatic imports from external APIs
- **Beautiful UI**: Clean, modern interface with Tailwind CSS
- **Family-Friendly**: Simple user activation without complex authentication
- **Smart Scoring**: Configurable points, lock bonuses, and leaderboards

### Built-in NBA Support
HindSight comes with full NBA integration:
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

1. **Environment Configuration (Optional):**
   
   Example config:

   ```env
   # Django Settings
   SECRET_KEY=your-secret-key-here
   DEBUG=True

   # Allowed Hosts (comma-separated)
   DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1,0.0.0.0

   # NBA API Configuration
   BALLDONTLIE_API_TOKEN=YOUR_TOKEN_HERE

   # User Selection (defaults to True if not set)
   ENABLE_USER_SELECTION=True

   # Page Customization (optional)
   PAGE_TITLE=HindSight
   PAGE_SLOGAN=Find out who's always right!

   HOOPTIPP_ADMIN_USER=hoop
   HOOPTIPP_ADMIN_PASSWORD=hoop
   PRIVACY_GATE_ANSWER=GSW,CLE,MIA
   ```

1. **Set up the database:**
   ```bash
   python manage.py migrate
   ```

1. **Run tests:**
   ```bash
   python manage.py test
   ```

1. **Start the server:**
   ```bash
   python manage.py runserver
   ```

1. **Access the app:**
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

## Deployment Modes

HindSight supports two deployment modes to fit different use cases:

### Mode 1: User Selection (Private/Family Use)
**Best for:** Private family deployments, small trusted groups

Set `ENABLE_USER_SELECTION=True` (default)

**Features:**
- Simple, family-friendly approach
- No authentication required on main page
- Users select themselves from a dropdown
- Optional privacy gate with NBA team challenge
- Optional per-user PIN protection
- Perfect for households where everyone is trusted

**Workflow:**
1. Admin creates users via Django admin panel
2. Users pass privacy gate (one-time NBA team challenge)
3. Users select themselves from dropdown
4. Make predictions
5. "Finish Round" to clear selection
6. Next user can then select themselves

### Mode 2: Authentication (Public Use)
**Best for:** Public-facing deployments, larger communities

Set `ENABLE_USER_SELECTION=False`

**Features:**
- Standard signup/login system
- Users create their own accounts
- Email-based account verification (required before first login)
- Email-based password reset
- Each user has private, secure access
- Traditional web app authentication
- Suitable for public internet deployment

**Workflow:**
1. Users sign up with username, email, and password
2. Verification email is sent to the user's email address
3. User clicks verification link in email to activate account
4. Users log in with credentials (only after verification)
5. Make predictions (automatically tied to logged-in user)
6. Log out when done

### Switching Between Modes

Simply change the `ENABLE_USER_SELECTION` environment variable:
```bash
# For private/family mode
ENABLE_USER_SELECTION=True

# For public authentication mode
ENABLE_USER_SELECTION=False
```

Both modes use the same codebase and database schema - no migrations needed!

## How Predictions Work

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

HindSight is designed for Railway deployment and supports both deployment modes:

### Private/Family Deployment (User Selection Mode)

```bash
# Core Settings
SECRET_KEY=your_secret_key_here
DATABASE_URL=postgresql://...
DJANGO_ALLOWED_HOSTS=yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com

# User Selection Mode
ENABLE_USER_SELECTION=True

# Privacy Gate (recommended for private deployments)
PRIVACY_GATE_ENABLED=True
PRIVACY_GATE_ANSWER=GSW,LAL,BOS,OKC

# NBA API (optional)
BALLDONTLIE_API_TOKEN=your_token

# Customization
PAGE_TITLE=Family Predictions
PAGE_SLOGAN=Who knows sports best?

# Admin Setup
HOOPTIPP_ADMIN_USER=admin
HOOPTIPP_ADMIN_PASSWORD=secure_password_here
```

### Public Deployment (Authentication Mode)

```bash
# Core Settings
SECRET_KEY=your_secret_key_here
DATABASE_URL=postgresql://...
DJANGO_ALLOWED_HOSTS=yourdomain.com
CSRF_TRUSTED_ORIGINS=https://yourdomain.com

# Authentication Mode
ENABLE_USER_SELECTION=False

# Privacy Gate (disable for public sites)
PRIVACY_GATE_ENABLED=False

# Email Configuration (for account verification and password reset)
# Option 1: AWS SES API (Recommended)
EMAIL_BACKEND=django_ses.SESBackend
AWS_SES_REGION_NAME=us-east-1
AWS_ACCESS_KEY_ID=your_aws_access_key
AWS_SECRET_ACCESS_KEY=your_aws_secret_key
DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# Option 2: AWS SES SMTP (Alternative)
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_USE_SSL=False
# EMAIL_HOST_USER=your_smtp_username
# EMAIL_HOST_PASSWORD=your_smtp_password
# DEFAULT_FROM_EMAIL=noreply@yourdomain.com
# EMAIL_TIMEOUT=30

# Option 3: Other SMTP (Gmail, etc.)
# EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
# EMAIL_HOST=smtp.gmail.com
# EMAIL_PORT=587
# EMAIL_USE_TLS=True
# EMAIL_HOST_USER=noreply@yourdomain.com
# EMAIL_HOST_PASSWORD=your_email_password
# DEFAULT_FROM_EMAIL=noreply@yourdomain.com

# NBA API (optional)
BALLDONTLIE_API_TOKEN=your_token

# Customization
PAGE_TITLE=HindSight
PAGE_SLOGAN=Predict. Compete. Win!

# Admin Setup
HOOPTIPP_ADMIN_USER=admin
HOOPTIPP_ADMIN_PASSWORD=secure_password_here
```

### Email Verification

When using Authentication Mode, new users must verify their email address before they can log in:

- After signup, a verification email is automatically sent
- Users click the verification link in the email (valid for 3 days)
- Once verified, users can log in normally
- If the email doesn't arrive, users can request a new verification email
- Password reset emails use the same email backend configuration

### AWS SES Setup

To use AWS SES for email delivery, you have two options:

#### Option 1: AWS SES API (Recommended)

1. **Verify your domain or email address** in AWS SES Console
   - Go to AWS SES Console → Verified identities
   - Add and verify your sending domain or email address

2. **Create IAM user with SES permissions**
   - Create an IAM user with `AmazonSESFullAccess` policy
   - Generate Access Key ID and Secret Access Key

3. **Configure environment variables** (see Public Deployment section above)

#### Option 2: AWS SES SMTP

1. **Verify your domain or email address** in AWS SES Console
   - Go to AWS SES Console → Verified identities
   - Add and verify your sending domain or email address

2. **Create SMTP credentials**
   - Go to AWS SES Console → SMTP settings
   - Click "Create SMTP credentials"
   - Download or copy the SMTP username and password
   - **Note**: The SMTP username and password are different from IAM access keys

3. **Find your SMTP endpoint**
   - Go to AWS SES Console → SMTP settings
   - Find your region's SMTP endpoint (e.g., `email-smtp.us-east-1.amazonaws.com`)
   - Note the port (587 for STARTTLS or 465 for SSL)

4. **Configure environment variables:**
   ```
   EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
   EMAIL_HOST=email-smtp.us-east-1.amazonaws.com
   EMAIL_PORT=587
   EMAIL_USE_TLS=True
   EMAIL_USE_SSL=False
   EMAIL_HOST_USER=your_smtp_username
   EMAIL_HOST_PASSWORD=your_smtp_password
   DEFAULT_FROM_EMAIL=noreply@yourdomain.com
   EMAIL_TIMEOUT=30
   ```

5. **Test your configuration:**
   ```bash
   python manage.py test_email --to your-email@example.com
   ```

**Common Issues:**
- **Socket connection error**: Check that EMAIL_HOST matches your AWS region (e.g., `email-smtp.us-east-1.amazonaws.com`)
- **Authentication error**: Verify SMTP username/password from SES Console (not IAM credentials)
- **Port 587**: Use `EMAIL_USE_TLS=True` and `EMAIL_USE_SSL=False`
- **Port 465**: Use `EMAIL_USE_SSL=True` and `EMAIL_USE_TLS=False`

#### AWS SES Sandbox Mode

**Important**: New AWS SES accounts start in **Sandbox mode**. In Sandbox mode:

- ✅ You can **only send emails to verified email addresses**
- ⚠️ Rate limits: **1 message/second** and **100 messages/day**
- ❌ You **cannot** send to unverified email addresses (like Gmail, Yahoo, etc.)

**If you get this error:**
```
Message rejected: Email address is not verified. The following identities failed the check
```

You have two options:

**Option A: Verify individual recipient emails (for testing)**
1. Go to [AWS SES Console](https://console.aws.amazon.com/ses/) → **Verified identities**
2. Click **"Create identity"** → Select **"Email address"**
3. Enter the recipient email address (e.g., `monsdar@gmail.com`)
4. Check that email's inbox for a verification email
5. Click the verification link in the email

**Option B: Request production access (recommended for production)**
1. Go to [AWS SES Console](https://console.aws.amazon.com/ses/) → **Account dashboard**
2. Scroll down to find **"Sending statistics"** section
3. Click **"Request production access"**
4. Fill out the request form:
   - Select your use case (e.g., "Transactional emails")
   - Describe your application and email content
   - Provide website URL if applicable
5. Submit the request (usually approved within 24 hours)
6. Once approved, you can send to any email address

**After moving to production:**
- ✅ Can send to **any email address**
- ✅ Higher rate limits (varies by region and account)
- ⚠️ Still must verify **sending** domain/email (the FROM address)

### Deploy to Railway

1. Connect your repository
2. Set environment variables based on your desired mode
3. Deploy!

The included `Dockerfile` and `docker-entrypoint.sh` handle the setup automatically.

---

## License

See [LICENSE](LICENSE) file for details.
