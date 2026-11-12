"""MySQL connection creation and FastAPI connection dependency."""
import mysql.connector
from mysql.connector import Error
from .config import DB_CONFIG


def get_connection():
    """Open one MySQL connection; callers are responsible for closing it."""
    return mysql.connector.connect(**DB_CONFIG)


def get_db():
    """Yield one connection per request and always close it afterwards."""
    connection = None
    try:
        connection = get_connection()
        yield connection
    except Error:
        if connection and connection.is_connected():
            connection.rollback()
        raise
    finally:
        if connection and connection.is_connected():
            connection.close()
