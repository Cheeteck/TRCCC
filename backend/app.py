import os
import sqlite3
import uuid
from datetime import datetime, timedelta

from PIL import Image
from flask import Flask, session, url_for
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from backend.roulette import roulette_numbers, spin_wheel, calculate_payout

app = Flask(__name__, static_folder='../frontend', static_url_path='')
app.secret_key = 'replace_with_a_strong_secret_key'  # Change this!

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATABASE = os.path.join(BASE_DIR, 'users.db')

def get_db_connection():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def migrate_db():
    conn = get_db_connection()
    try:
        conn.execute('ALTER TABLE users ADD COLUMN daily_streak INTEGER NOT NULL DEFAULT 1')
        conn.commit()
    except sqlite3.OperationalError:
        # Column already exists or other issue; ignore
        pass
    conn.close()

migrate_db()  # Run once on startup


def init_db():
    conn = get_db_connection()
    conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            uid TEXT UNIQUE NOT NULL,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            balance INTEGER NOT NULL DEFAULT 1000,
            last_claim TEXT,
            daily_streak INTEGER NOT NULL DEFAULT 1
        )
    ''')
    conn.commit()
    conn.close()

init_db()

from cryptography.fernet import Fernet

# Password shit
fernet_key = b'aEO1s5dPLCLqir34SA57Q1wwgBI0bwMgOc-XWeTeanY='
fernet = Fernet(fernet_key)

def encrypt_password(password):
    return fernet.encrypt(password.encode()).decode()

def decrypt_password(token):
    return fernet.decrypt(token.encode()).decode()

# Profile pics

def migrate_db():
    conn = get_db_connection()
    try:
        conn.execute('ALTER TABLE users ADD COLUMN profile_pic TEXT')
        conn.commit()
    except sqlite3.OperationalError:
        pass
    conn.close()



def get_current_user():
    uid = session.get('uid')
    if not uid:
        return None, None
    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE uid = ?', (uid,)).fetchone()
    conn.close()
    return uid, user

def get_leaderboard():
    conn = get_db_connection()
    users = conn.execute('SELECT username, balance, profile_pic FROM users ORDER BY balance DESC LIMIT 10').fetchall()
    conn.close()
    return [{'username': u['username'], 'balance': u['balance'], 'profile_pic': u['profile_pic']} for u in users]


@app.route('/register')
def register_page():
    return send_from_directory(app.static_folder, 'register.html')

@app.route('/register', methods=['POST'])
def register():
    data = request.json
    username = data.get('username', '').strip()
    password = data.get('password', '')

    if not username or not password:
        return jsonify({'error': 'Username and password required'}), 400

    conn = get_db_connection()
    existing = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    if existing:
        conn.close()
        return jsonify({'error': 'Username already exists'}), 400

    hashed_password = generate_password_hash(password)
    uid = str(uuid.uuid4())
    conn.execute(
        'INSERT INTO users (uid, username, password, balance, last_claim, daily_streak) VALUES (?, ?, ?, ?, ?, ?)',
        (uid, username, hashed_password, 1000, None, 1)
    )
    conn.commit()
    conn.close()

    session['uid'] = uid
    return jsonify({'message': f'User {username} registered and logged in successfully!'})

@app.route('/login')
def login_page():
    return send_from_directory(app.static_folder, 'login.html')

@app.route('/login', methods=['POST'])
def login():
    data = request.json
    username = data.get('username')
    password = data.get('password')

    conn = get_db_connection()
    user = conn.execute('SELECT * FROM users WHERE username = ?', (username,)).fetchone()
    conn.close()

    if not user or not check_password_hash(user['password'], password):
        return jsonify({'error': 'Invalid username or password'}), 401

    session['uid'] = user['uid']
    return jsonify({'message': 'Logged in successfully'})

@app.route('/logout', methods=['POST'])
def logout():
    session.pop('uid', None)
    return jsonify({'message': 'Logged out'})

@app.route('/')
def home():
    uid = session.get('uid')
    if not uid:
        return redirect(url_for('login_page'))
    return send_from_directory(app.static_folder, 'index.html')


# ------------------------------------------------------------  Account page -----------------------------------------------

UPLOAD_FOLDER = 'uploads/profile_pics'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/account')
def account_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'account.html')

@app.route('/account/info')
def account_info():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    return jsonify({
        'uid': uid,
        'username': user['username'],
        'balance': user['balance'],
        'last_claim': user['last_claim'],
        'daily_streak': user['daily_streak'],
        'profile_pic': user['profile_pic']
    })

@app.route('/account/upload_pfp', methods=['POST'])
def upload_profile_pic():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    if 'profile_pic' not in request.files:
        return jsonify({'error': 'No file uploaded'}), 400

    file = request.files['profile_pic']
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        # Save original temporarily
        temp_path = os.path.join(UPLOAD_FOLDER, f'temp_{uid}.tmp')
        file.save(temp_path)

        # Convert & crop to WebP
        webp_filename = f'{uid}.webp'
        webp_path = os.path.join(UPLOAD_FOLDER, webp_filename)

        with Image.open(temp_path) as img:
            img = img.convert('RGBA')
            width, height = img.size
            min_dim = min(width, height)
            left = (width - min_dim) // 2
            top = (height - min_dim) // 2
            right = left + min_dim
            bottom = top + min_dim
            img_cropped = img.crop((left, top, right, bottom)).resize((256, 256), Image.LANCZOS)
            img_cropped.save(webp_path, 'webp', quality=85)

        os.remove(temp_path)

        # Update user record
        conn = get_db_connection()
        conn.execute('UPDATE users SET profile_pic = ? WHERE uid = ?', (webp_filename, uid))
        conn.commit()
        conn.close()

        return jsonify({'message': 'Profile picture uploaded successfully', 'profile_pic': webp_filename})

    return jsonify({'error': 'Invalid file type'}), 400


@app.route('/profile_pics/<filename>')
def serve_profile_pic(filename):
    return send_from_directory('uploads/profile_pics', filename)


from datetime import datetime, timedelta, timezone

@app.route('/account/claim_daily', methods=['POST'])
def claim_daily():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    now = datetime.now(timezone.utc)  # timezone-aware current UTC datetime

    last_claim_str = user['last_claim']
    daily_streak = user['daily_streak']

    if last_claim_str:
        last_claim_dt = datetime.fromisoformat(last_claim_str)
        # Ensure last_claim_dt is timezone-aware in UTC
        if last_claim_dt.tzinfo is None:
            last_claim_dt = last_claim_dt.replace(tzinfo=timezone.utc)

        delta = now - last_claim_dt

        if delta < timedelta(hours=24):
            remaining = timedelta(hours=24) - delta
            # Format remaining nicely hh:mm:ss without microseconds
            remaining_str = str(remaining).split('.')[0]
            return jsonify({
                'error': f'Claim cooldown active. Try again in {remaining_str}'
            }), 429

        if delta < timedelta(hours=48):
            daily_streak += 1
        else:
            daily_streak = 1
    else:
        daily_streak = 1

    reward = 1500 + 1000 * (daily_streak - 1)

    conn = get_db_connection()
    conn.execute(
        'UPDATE users SET balance = balance + ?, last_claim = ?, daily_streak = ? WHERE uid = ?',
        (reward, now.isoformat(), daily_streak, uid)
    )
    conn.commit()
    conn.close()

    new_balance = user['balance'] + reward

    return jsonify({
        'message': f'Daily {reward} chips claimed!',
        'new_balance': new_balance
    })
# -------------------------------------Snake Eyes -------------------------------------------
@app.route('/snake_eyes_roll', methods=['POST'])
def snake_eyes_roll():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    bet = data.get('bet')
    if not isinstance(bet, int) or bet <= 0 or bet > user['balance']:
        return jsonify({'error': 'Invalid bet amount'}), 400

    dice1 = random.randint(1, 6)
    dice2 = random.randint(1, 6)

    # Calculate payout based on dice
    if dice1 == 1 and dice2 == 1:
        multiplier = 12
        payout = bet * multiplier
        win = True
    elif dice1 == 1 or dice2 == 1:
        multiplier = 1.25
        payout = int(bet * multiplier)
        win = True
    else:
        payout = 0
        win = False

    new_balance = user['balance'] - bet + payout

    # Update new balance in database
    conn = get_db_connection()
    conn.execute('UPDATE users SET balance = ? WHERE uid = ?', (new_balance, uid))
    conn.commit()
    conn.close()

    return jsonify({
        'dice1': dice1,
        'dice2': dice2,
        'payout': payout,
        'new_balance': new_balance,
        'win': win,
        'multiplier': multiplier if win else 0
    })

@app.route('/snake-eyes')
def snake_eyes_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'snake-eyes.html')

 # ------------------------------------- Account end -------------------------------------------
@app.route('/balance')
def get_balance():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401
    return jsonify({'balance': user['balance']})

@app.route('/coinflip')
def coinflip_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'coinflip.html')

@app.route('/coinflip', methods=['POST'])
def coinflip_logic():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    bet = data.get('bet')
    choice = data.get('choice')
    win_chance = data.get('winChance', 0.5)

    if bet is None or choice not in ['heads', 'tails'] or bet > user['balance'] or bet <= 0:
        return jsonify({'error': 'Invalid bet or choice'}), 400

    player_wins = random.random() < win_chance

    new_balance = user['balance']
    if player_wins:
        flip_result = choice
        new_balance += bet
        result = 'win'
    else:
        flip_result = 'tails' if choice == 'heads' else 'heads'
        new_balance -= bet
        result = 'lose'

    conn = get_db_connection()
    conn.execute('UPDATE users SET balance = ? WHERE uid = ?', (new_balance, uid))
    conn.commit()
    conn.close()

    return jsonify({
        'result': result,
        'flip_result': flip_result,
        'new_balance': new_balance
    })

@app.route('/roulette')
def roulette_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'roulette.html')

@app.route('/roulette_bet', methods=['POST'])
def roulette_bet():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    bet_amount = data.get('bet', 0)
    bets = data.get('bets', {})

    if bet_amount <= 0 or not bets:
        return jsonify({'error': 'Invalid bet'}), 400

    if user['balance'] < bet_amount:
        return jsonify({'error': 'Insufficient balance'}), 400

    spin_result = spin_wheel()
    payout, total_bet, net_profit = calculate_payout(bets, spin_result)

    new_balance = user['balance'] - total_bet + payout

    conn = get_db_connection()
    conn.execute('UPDATE users SET balance = ? WHERE uid = ?', (new_balance, uid))
    conn.commit()
    conn.close()

    result_index = next((i for i, val in enumerate(roulette_numbers) if val['num'] == spin_result['num']), 0)
    result_text = "WIN" if payout > 0 else "LOSE"

    return jsonify({
        'result_num': spin_result['num'],
        'result_color': spin_result['color'],
        'result_index': result_index,
        'payout': payout,
        'new_balance': new_balance,
        'result_text': result_text
    })
# ---------------------------------------------------------------------- Slots ------------------------------
symbols = ['mark', 'lemon', 'cheet', 'snackbag', 'kam', 'tophat', 'beaver']


@app.route('/slots')
def slots_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'slots.html')

@app.route('/slots_spin', methods=['POST'])
def slots_spin():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    bet = data.get('bet')

    if bet is None or not isinstance(bet, int) or bet <= 0 or bet > user['balance']:
        return jsonify({'error': 'Invalid bet amount'}), 400

    new_balance = user['balance'] - bet

    # Roll three random symbols (now using string IDs)
    spin_result = [random.choice(symbols) for _ in range(3)]

    # Calculate payout: 3 matches = 5x, 2 matches = 2x, else 0
    if spin_result[0] == spin_result[1] == spin_result[2]:
        payout = bet * 5
    elif (spin_result[0] == spin_result[1] or
          spin_result[1] == spin_result[2] or
          spin_result[0] == spin_result[2]):
        payout = bet * 2
    else:
        payout = 0

    new_balance += payout

    # Update user balance in database
    conn = get_db_connection()
    conn.execute('UPDATE users SET balance = ? WHERE uid = ?', (new_balance, uid))
    conn.commit()
    conn.close()

    result = 'win' if payout > 0 else 'lose'
    # spin_result will be a list like ['star', 'lemon', 'lemon']

    return jsonify({
        'result': result,
        'spin_result': spin_result,   # these are image IDs for the FE!
        'payout': payout,
        'new_balance': new_balance
    })
# ------------------------------- Admin-------------------------------------

admin_uid = 'b45544cf-2535-40d3-a087-eb267598be5c'

def is_admin(uid):
    return uid == admin_uid

@app.route('/admin/all_users')
def admin_all_users():
    uid, user = get_current_user()
    if not user or not is_admin(uid):
        return jsonify({'error': 'Unauthorized'}), 403

    conn = get_db_connection()
    users = conn.execute('SELECT uid, username, balance, last_claim, daily_streak FROM users').fetchall()
    conn.close()
    return jsonify([dict(u) for u in users])

@app.route('/admin/update_user', methods=['POST'])
def admin_update_user():
    uid, user = get_current_user()
    if not user or not is_admin(uid):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json or {}
    target_uid = data.get('uid')
    if not target_uid:
        return jsonify({'error': 'Missing user ID'}), 400

    updates = {}
    # Validate and prepare fields
    if 'balance' in data:
        try:
            updates['balance'] = int(data['balance'])
        except Exception:
            return jsonify({'error': 'Invalid balance'}), 400
    if 'last_claim' in data:
        updates['last_claim'] = data.get('last_claim')  # Expect ISO8601 string or None
    if 'daily_streak' in data:
        try:
            updates['daily_streak'] = int(data['daily_streak'])
        except Exception:
            return jsonify({'error': 'Invalid daily_streak'}), 400

    if not updates:
        return jsonify({'error': 'No fields to update'}), 400

    set_clause = ', '.join([f"{k} = ?" for k in updates.keys()])
    values = list(updates.values())
    values.append(target_uid)

    conn = get_db_connection()
    conn.execute(f'UPDATE users SET {set_clause} WHERE uid = ?', values)
    conn.commit()
    conn.close()
    return jsonify({'message': 'User updated successfully'})

@app.route('/admin/delete_user', methods=['POST'])
def admin_delete_user():
    uid, user = get_current_user()
    if not user or not is_admin(uid):
        return jsonify({'error': 'Unauthorized'}), 403

    data = request.json or {}
    target_uid = data.get('uid')
    if not target_uid:
        return jsonify({'error': 'Missing user ID'}), 400

    conn = get_db_connection()
    conn.execute('DELETE FROM users WHERE uid = ?', (target_uid,))
    conn.commit()
    conn.close()
    return jsonify({'message': 'User deleted successfully'})


# ---------------------------- Lottery ---------------------
import random
import threading
import atexit
import logging

from flask import request, jsonify, redirect, send_from_directory

from apscheduler.schedulers.background import BackgroundScheduler

# Constants for the lottery
MAX_TICKETS_PER_ROUND = 100_000_000
TICKET_PRICE = 150
MAX_TICKETS_PER_PURCHASE = 100_000  # to prevent abuse

PRIZE_POOLS = [1_000_000, 5_000_000, 10_000_000, 15_000_000, 20_000_000]

# Setup logger for lottery subsystem
logger = logging.getLogger('lottery')
if not logger.hasHandlers():
    logging.basicConfig(level=logging.INFO)

# Assume you already have these helper functions in your app:
# get_current_user() -> (uid, user_dict) or (None, None)
# get_db_connection() -> SQLite connection

class Lottery:
    def __init__(self):
        self.lock = threading.Lock()
        self.current_round = 0
        self.prize_pool = PRIZE_POOLS[self.current_round]
        self.tickets = {}  # ticket_number(int) -> user_id(str)
        self.tickets_sold = 0

    def get_tickets_left(self):
        return MAX_TICKETS_PER_ROUND - self.tickets_sold

    def get_user_tickets(self, user_id):
        return sorted([t for t, uid in self.tickets.items() if uid == user_id])

    def buy_tickets(self, user_id, amount, user_balance):
        cost = amount * TICKET_PRICE

        if amount <= 0:
            return False, "You must buy at least 1 ticket.", None
        if amount > MAX_TICKETS_PER_PURCHASE:
            return False, f"You can buy at most {MAX_TICKETS_PER_PURCHASE} tickets at once.", None
        if user_balance < cost:
            return False, "Insufficient chips to buy tickets.", None
        if self.get_tickets_left() < amount:
            return False, f"Only {self.get_tickets_left()} tickets left this round.", None

        assigned_tickets = set()
        tries = 0
        max_tries = amount * 20  # avoid infinite loops if nearly sold out

        with self.lock:
            while len(assigned_tickets) < amount and tries < max_tries:
                ticket_num = random.randint(1, MAX_TICKETS_PER_ROUND)
                if ticket_num not in self.tickets and ticket_num not in assigned_tickets:
                    assigned_tickets.add(ticket_num)
                tries += 1

            if len(assigned_tickets) < amount:
                return False, "Could not assign enough unique tickets, try fewer.", None

            for t in assigned_tickets:
                self.tickets[t] = user_id
            self.tickets_sold += amount

        return True, None, sorted(assigned_tickets)

    def draw_winner(self):
        with self.lock:
            if self.tickets_sold == 0:
                # No tickets sold, rollover prize pool
                self.current_round = min(self.current_round + 1, len(PRIZE_POOLS) - 1)
                self.prize_pool = PRIZE_POOLS[self.current_round]
                self.tickets.clear()
                self.tickets_sold = 0
                logger.info(f"No tickets sold. Prize pool rolled over to {self.prize_pool}.")
                return None, None

            winning_ticket = random.randint(1, MAX_TICKETS_PER_ROUND)
            winner = self.tickets.get(winning_ticket)

            if winner:
                prize = self.prize_pool
                logger.info(f"Lottery winner: user {winner} with ticket #{winning_ticket}, prize {prize} chips.")

                # Reset lottery
                self.current_round = 0
                self.prize_pool = PRIZE_POOLS[self.current_round]
                self.tickets.clear()
                self.tickets_sold = 0
                return winner, prize
            else:
                # No winner; increase prize pool and reset
                self.current_round = min(self.current_round + 1, len(PRIZE_POOLS) - 1)
                self.prize_pool = PRIZE_POOLS[self.current_round]
                self.tickets.clear()
                self.tickets_sold = 0
                logger.info(f"No winner for ticket #{winning_ticket}. Prize pool rolled over to {self.prize_pool}.")
                return None, None


# Instantiate the Lottery singleton
lottery = Lottery()

# --- Flask Routes for Lottery ---

@app.route('/lottery')
def lottery_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'lottery.html')

@app.route('/lottery_status')
def lottery_status():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    return jsonify({
        'prize_pool': lottery.prize_pool,
        'tickets_left': lottery.get_tickets_left(),
        'user_tickets': lottery.get_user_tickets(uid)
    })

@app.route('/lottery_buy', methods=['POST'])
def lottery_buy():
    uid, user = get_current_user()
    if not user:
        return jsonify({'error': 'Not logged in'}), 401

    data = request.json
    amount = data.get('amount')
    if not isinstance(amount, int):
        return jsonify({'error': 'Invalid ticket amount'}), 400

    success, error_msg, assigned_tickets = lottery.buy_tickets(uid, amount, user['balance'])
    if not success:
        return jsonify({'error': error_msg}), 400

    # Deduct user's balance accordingly
    new_balance = user['balance'] - amount * TICKET_PRICE
    conn = get_db_connection()
    conn.execute('UPDATE users SET balance = ? WHERE uid = ?', (new_balance, uid))
    conn.commit()
    conn.close()

    return jsonify({
        'assigned_tickets': assigned_tickets,
        'prize_pool': lottery.prize_pool,
        'tickets_left': lottery.get_tickets_left()
    })


# --- Scheduled Hourly Draw ---

def run_lottery_draw():
    with app.app_context():
        logger.info("Running scheduled lottery draw.")
        winner_id, prize = lottery.draw_winner()

        if winner_id and prize:
            conn = get_db_connection()
            cur = conn.execute('SELECT balance FROM users WHERE uid = ?', (winner_id,))
            row = cur.fetchone()
            if row:
                updated_balance = row['balance'] + prize
                conn.execute('UPDATE users SET balance = ? WHERE uid = ?', (updated_balance, winner_id))
                conn.commit()
                logger.info(f"Credited user {winner_id} with {prize} chips. New balance: {updated_balance}.")
            else:
                logger.error(f"Winner user {winner_id} not found in DB.")
            conn.close()
            # TODO: Add notification or broadcast to users if desired
        else:
            logger.info("No winner this lottery draw. Prize pool rolled over.")

scheduler = BackgroundScheduler()
scheduler.add_job(run_lottery_draw, 'cron', minute=0)  # every hour on the hour
scheduler.start()
logger.info("Started APScheduler for lottery draw job.")

atexit.register(lambda: scheduler.shutdown())



@app.route('/tos')
def tos_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'tos.html')

@app.route('/privacy')
def privacy_page():
    uid, user = get_current_user()
    if not user:
        return redirect('/login')
    return send_from_directory(app.static_folder, 'privacy.html')

@app.route('/leaderboard')
def leaderboard_route():
    return jsonify({'leaderboard': get_leaderboard()})



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
