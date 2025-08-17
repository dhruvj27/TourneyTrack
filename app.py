from flask import Flask, render_template, request, redirect, url_for, session, flash
from models import db, User, Tournament, Team, Player, Match
from datetime import datetime, timedelta
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'dev-key-2024-tourneytrack'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///tournament.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

@app.route('/')
def index():
    return render_template("index.html")

if __name__=="__main__":
    app.run(debug=True,port=5000)