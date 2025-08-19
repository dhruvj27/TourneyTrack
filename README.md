# TourneyTrack: A Smart Tournament Management System

TourneyTrack is a prototype system designed to manage sports tournaments digitally. It includes features like team registration, match scheduling, result announcements, and viewing fixtures and results, streamlining tournament organization for both organizers and participants.

---

## Features
- **Register Player/Team:** SMC can register teams and their players for the tournament.
- **Update Team/Player Profile:** Team managers can update team details and manage player profiles.
- **Schedule Matches:** SMC can schedule matches between teams with conflict validation.
- **View Upcoming Fixtures:** Viewers can see upcoming fixtures and past results.
- **Result Announcements:** SMC can record and announce match results.

---

## Requirements
- Python 3.8 or higher
- Flask
- Flask-SQLAlchemy
- SQLite (default database)

---

## Setup Instructions

### 1. Clone the Repository
```bash
git clone https://github.com/dhruvj27/TourneyTrack.git
cd TourneyTrack
```

### 2. Create a Virtual Environment
```bash
python -m venv venv
```

### 3. Activate the Virtual Environment
- **Windows:**
  ```bash
  venv\Scripts\activate
  ```
- **Mac/Linux:**
  ```bash
  source venv/bin/activate
  ```

### 4. Install Dependencies
```bash
pip install -r [requirements.txt]
```

### 5. Run the Application
```bash
set FLASK_APP=app.py
flask run
```

### 6. Access the Application
Open your browser and navigate to: [http://127.0.0.1:5000](http://127.0.0.1:5000)
