from flask import Flask, request, render_template
import sqlite3

app = Flask(__name__)

# Создаем подключение к базе данных SQLite
conn = sqlite3.connect('userdata.db', check_same_thread=False)
cursor = conn.cursor()

@app.route('/webapp', methods=['GET'])
def webapp():
    user_id = request.args.get('user_id')
    cursor.execute('SELECT steps FROM users WHERE user_id = ?', (user_id,))
    result = cursor.fetchone()
    steps = result[0] if result else 0
    return render_template('index.html', steps=steps, user_id=user_id)

if __name__ == '__main__':
    app.run(debug=True)
