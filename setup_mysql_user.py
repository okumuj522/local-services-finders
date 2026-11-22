"""Create a dedicated, least-privilege MySQL account for Local Services Finder."""

import getpass

import mysql.connector
from mysql.connector import Error


def main():
    host = input("MySQL host [localhost]: ").strip() or "localhost"
    port_text = input("MySQL port [3306]: ").strip() or "3306"
    admin_user = input("MySQL administrator username [root]: ").strip() or "root"
    admin_password = getpass.getpass("MySQL administrator password: ")
    app_password = getpass.getpass("New Local Services Finder database password (12+ characters): ")
    confirm_password = getpass.getpass("Confirm new database password: ")

    if len(app_password) < 12:
        print("Choose a database password with at least 12 characters.")
        return
    if app_password != confirm_password:
        print("The passwords do not match.")
        return

    connection = None
    cursor = None
    try:
        connection = mysql.connector.connect(
            host=host,
            port=int(port_text),
            user=admin_user,
            password=admin_password,
        )
        cursor = connection.cursor()
        cursor.execute(
            "CREATE DATABASE IF NOT EXISTS local_services "
            "CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"
        )
        cursor.execute(
            "CREATE USER IF NOT EXISTS 'local_services_app'@'localhost' IDENTIFIED BY %s",
            (app_password,),
        )
        cursor.execute(
            "ALTER USER 'local_services_app'@'localhost' IDENTIFIED BY %s",
            (app_password,),
        )
        cursor.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE, CREATE, ALTER, INDEX, REFERENCES "
            "ON local_services.* TO 'local_services_app'@'localhost'"
        )
        connection.commit()
        print("Database and dedicated app account are ready.")
        print("Use MYSQL_USER=local_services_app and MYSQL_DATABASE=local_services when starting the app.")
    except (ValueError, Error) as error:
        print(f"MySQL setup failed: {error}")
    finally:
        if cursor is not None:
            cursor.close()
        if connection is not None and connection.is_connected():
            connection.close()


if __name__ == "__main__":
    main()
