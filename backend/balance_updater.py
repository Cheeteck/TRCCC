import sqlite3

DATABASE = 'users.db'

def update_balance(username, new_balance):
    conn = sqlite3.connect(DATABASE)
    try:
        cursor = conn.cursor()
        cursor.execute('UPDATE users SET balance = ? WHERE username = ?', (new_balance, username))
        conn.commit()
        print(f"Balance for user '{username}' updated to {new_balance}.")
    except Exception as e:
        print(f"Error updating balance: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_balance('Cheeteck', 10000)
