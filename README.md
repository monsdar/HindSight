# 🏀 HoopTipp

**HoopTipp** is a simple, private and self-hosted, family-friendly NBA prediction app. It was created to have a way for predicting the upcoming NBA season with my son — without spreadsheets, complicated fantasy rules, or cluttered interfaces.

---

## 🎯 Vision

> **Sunday night = Prediction night.**
> Pick the biggest games of the upcoming week, guess player of the match, make season predictions for All-Stars, MVP and other individual honors, and find out who’s the true NBA Tip Master by the end of the year.

HoopTipp is designed for families and fans who want a **lightweight, engaging way** to experience the NBA season together.

---

## 👥 Target Audience

- 🧒 Kids and young NBA fans, moderated by family members
- 👨‍👩‍👧‍👦 Families who want a fun, recurring NBA activity
- 🏀 Casual or dedicated fans who enjoy predictions without the complexity of fantasy leagues

---

## 🧩 Core Features

### 1. 🗓 Weekly Game Picks
- Every Sunday, **5–7 highlight games** for the upcoming week are published.
- Users pick **home or away winners**, with an optional **lock game** option for games where users are very confident.
- Picks lock automatically before the first game starts.
- **Scoring:** 2 points per correct pick + lock bonus.

---

### 2. 📅 Monthly Picks
- At the start of each month, users predict:
  - **Players of the Month (East, West)**
  - **Teams of the month (East, West)**
- Points are awarded at the end of the month:
  - 5 points for correctly predicting Players of the Month
  - 3 points if the selected team finishes in the top 3 for wins

---

### 3. 🏆 Season Awards & All-Stars
- Before Christmas, users can predict:
  - **All-Stars**, **MVP**, **Rookie of the Year**, **DPOY**, **MIP**, etc.
- Points are awarded once official results are known.

---

### 4. 🌳 Playoff Bracket
- Once the playoff bracket is set, users predict the **entire playoffs**.
- Points increase by round, adding extra excitement for the postseason.

---

### 5. 📊 Scoreboard & Badges
- A **live leaderboard** tracks total points throughout the season.
- Users can earn **achievement badges** for milestones (e.g. “Perfect Week”, “Upset King”).

---

## 🚀 Predicting

To support multiple users the game works with a simplified user-activation: 

* All users are created via the admin panel
* By default no user is selected in the UI. Upcoming predictions are visible, along with users that already predicted an outcome.
* A user can be activated within the UI. There's is no complex authentication needed.
* When activated a user can predict the outcome of the available tipps.
* After predictions the user simply deactivates himself, the UI then returns to a neutral state

## Development
### Local Setup

1. Create a virtual environment and install dependencies:

   ```bash
   python -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Prepare the database and create a superuser:

   ```bash
   python manage.py migrate
   python manage.py createsuperuser
   ```

3. Run the Django unit tests:

   ```bash
   python manage.py test
   ```

4. Start the development server:

   ```bash
   python manage.py runserver
   ```

5. Use `/admin` to create or manage users. On the homepage you can choose an active user whose picks are stored for the weekly games.

> Note: The `nba_api` package is required to fetch NBA data. This package does not work when running from within one of the hyperscalers.
