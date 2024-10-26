import mysql.connector

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="root",
        database="ml_food_app"
    )

def initialize_database():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS items (
                      id INT AUTO_INCREMENT PRIMARY KEY,
                      name VARCHAR(100),
                      price FLOAT,
                      image VARCHAR(255),
                      demand INT,
                      stock INT
                      )''')
    conn.commit()
    cursor.close()
    conn.close()
