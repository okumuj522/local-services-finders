"""A small Python-only directory for finding local service providers."""

import argparse
import os
import mysql.connector
from mysql.connector import Error


def connect():
    db = mysql.connector.connect(
        host=os.getenv("MYSQL_HOST", "localhost"),
        port=int(os.getenv("MYSQL_PORT", "3306")),
        user=os.getenv("MYSQL_USER", "local_services_app"),
        password=os.getenv("MYSQL_PASSWORD", ""),
        database=os.getenv("MYSQL_DATABASE", "local_services"),
    )
    cursor = db.cursor()
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS providers (
               id INT AUTO_INCREMENT PRIMARY KEY,
               name TEXT NOT NULL,
               service TEXT NOT NULL,
               location TEXT NOT NULL,
               phone TEXT NOT NULL,
               price TEXT,
               notes TEXT,
               opening_hours TEXT,
               website TEXT,
               verified TINYINT NOT NULL DEFAULT 0,
               latitude DECIMAL(10, 7) NULL,
               longitude DECIMAL(10, 7) NULL
           )"""
    )
    cursor.execute("SHOW COLUMNS FROM providers")
    provider_columns = {column[0] for column in cursor.fetchall()}
    if "latitude" not in provider_columns:
        cursor.execute("ALTER TABLE providers ADD COLUMN latitude DECIMAL(10, 7) NULL")
    if "longitude" not in provider_columns:
        cursor.execute("ALTER TABLE providers ADD COLUMN longitude DECIMAL(10, 7) NULL")
    if "opening_hours" not in provider_columns:
        cursor.execute("ALTER TABLE providers ADD COLUMN opening_hours TEXT NULL")
    if "website" not in provider_columns:
        cursor.execute("ALTER TABLE providers ADD COLUMN website TEXT NULL")
    if "verified" not in provider_columns:
        cursor.execute("ALTER TABLE providers ADD COLUMN verified TINYINT NOT NULL DEFAULT 0")
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS reviews (
               id INT AUTO_INCREMENT PRIMARY KEY,
               provider_id INT NOT NULL,
               reviewer TEXT NOT NULL,
               rating TINYINT NOT NULL,
               comment TEXT NOT NULL,
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               CONSTRAINT fk_reviews_provider FOREIGN KEY (provider_id)
                   REFERENCES providers(id) ON DELETE CASCADE
           )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS provider_reports (
               id INT AUTO_INCREMENT PRIMARY KEY,
               provider_id INT NOT NULL,
               reporter VARCHAR(255) NOT NULL,
               issue VARCHAR(100) NOT NULL,
               details TEXT NOT NULL,
               status VARCHAR(20) NOT NULL DEFAULT 'open',
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               CONSTRAINT fk_reports_provider FOREIGN KEY (provider_id)
                   REFERENCES providers(id) ON DELETE CASCADE
           )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS admins (
               id INT AUTO_INCREMENT PRIMARY KEY,
               username VARCHAR(100) NOT NULL UNIQUE,
               password_salt CHAR(32) NOT NULL,
               password_hash CHAR(64) NOT NULL,
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
           )"""
    )
    cursor.execute(
        """CREATE TABLE IF NOT EXISTS service_requests (
               id INT AUTO_INCREMENT PRIMARY KEY,
               tracking_code VARCHAR(32) NULL UNIQUE,
               provider_id INT NOT NULL,
               requester_name VARCHAR(255) NOT NULL,
               phone VARCHAR(50) NOT NULL,
               preferred_time VARCHAR(100) NOT NULL,
               description TEXT NOT NULL,
               admin_response TEXT NULL,
               privacy_consent_at TIMESTAMP NULL,
               status VARCHAR(20) NOT NULL DEFAULT 'pending',
               created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
               CONSTRAINT fk_requests_provider FOREIGN KEY (provider_id)
                   REFERENCES providers(id) ON DELETE CASCADE
           )"""
    )
    cursor.execute("SHOW COLUMNS FROM service_requests")
    request_columns = {column[0] for column in cursor.fetchall()}
    if "tracking_code" not in request_columns:
        cursor.execute("ALTER TABLE service_requests ADD COLUMN tracking_code VARCHAR(32) NULL UNIQUE")
    if "admin_response" not in request_columns:
        cursor.execute("ALTER TABLE service_requests ADD COLUMN admin_response TEXT NULL")
    if "privacy_consent_at" not in request_columns:
        cursor.execute("ALTER TABLE service_requests ADD COLUMN privacy_consent_at TIMESTAMP NULL")
    cursor.execute("UPDATE service_requests SET tracking_code = CONCAT('LSF-', LPAD(id, 8, '0')) WHERE tracking_code IS NULL")
    cursor.close()
    return db


def add_provider(args):
    with connect() as db:
        cursor = db.cursor()
        cursor.execute(
            "INSERT INTO providers (name, service, location, phone, price, notes) VALUES (%s, %s, %s, %s, %s, %s)",
            (args.name, args.service, args.location, args.phone, args.price, args.notes),
        )
        db.commit()
        cursor.close()
    print(f"Added {args.name} ({args.service}) in {args.location}.")


def search_providers(args):
    query = """SELECT p.*, COUNT(r.id) AS review_count, AVG(r.rating) AS average_rating
               FROM providers p LEFT JOIN reviews r ON r.provider_id = p.id
               WHERE p.service LIKE %s AND p.location LIKE %s
               GROUP BY p.id ORDER BY p.name"""
    with connect() as db:
        cursor = db.cursor(dictionary=True)
        cursor.execute(query, (f"%{args.service}%", f"%{args.location}%"))
        rows = cursor.fetchall()
        cursor.close()
    if not rows:
        print("No providers found. Try a broader service or location, or add a provider.")
        return
    for row in rows:
        print(f"\n{row['name']} — {row['service']}")
        print(f"  Area: {row['location']} | Phone: {row['phone']}")
        if row["review_count"]:
            print(f"  Rating: {row['average_rating']:.1f}/5 ({row['review_count']} reviews)")
        else:
            print("  Rating: No reviews yet")
        if row["price"]:
            print(f"  Price: {row['price']}")
        if row["notes"]:
            print(f"  Notes: {row['notes']}")


def list_providers(_args):
    with connect() as db:
        cursor = db.cursor(dictionary=True)
        cursor.execute(
            """SELECT p.*, COUNT(r.id) AS review_count, AVG(r.rating) AS average_rating
               FROM providers p LEFT JOIN reviews r ON r.provider_id = p.id
               GROUP BY p.id ORDER BY p.service, p.location, p.name"""
        )
        rows = cursor.fetchall()
        cursor.close()
    if not rows:
        print("The directory is empty. Add a provider to get started.")
        return
    for row in rows:
        rating = f"{row['average_rating']:.1f}/5" if row["review_count"] else "no ratings"
        print(f"{row['id']}. {row['name']} — {row['service']} in {row['location']} ({row['phone']}; {rating})")


def add_review(args):
    with connect() as db:
        cursor = db.cursor(dictionary=True)
        cursor.execute("SELECT name FROM providers WHERE id = %s", (args.provider_id,))
        provider = cursor.fetchone()
        if provider is None:
            print(f"No provider found with ID {args.provider_id}.")
            return
        cursor.execute(
            "INSERT INTO reviews (provider_id, reviewer, rating, comment) VALUES (%s, %s, %s, %s)",
            (args.provider_id, args.reviewer, args.rating, args.comment),
        )
        db.commit()
        cursor.close()
    print(f"Review added for {provider['name']}.")


def build_parser():
    parser = argparse.ArgumentParser(description="Find and save local service providers.")
    commands = parser.add_subparsers(dest="command", required=True)

    add = commands.add_parser("add", help="Add a provider to the directory")
    add.add_argument("--name", required=True, help="Provider or business name")
    add.add_argument("--service", required=True, help="For example, plumber")
    add.add_argument("--location", required=True, help="Neighborhood or town")
    add.add_argument("--phone", required=True, help="Contact number")
    add.add_argument("--price", default="", help="Optional price information")
    add.add_argument("--notes", default="", help="Optional notes")
    add.set_defaults(run=add_provider)

    search = commands.add_parser("search", help="Search by service and location")
    search.add_argument("--service", default="", help="Service to find")
    search.add_argument("--location", default="", help="Area to search")
    search.set_defaults(run=search_providers)

    show = commands.add_parser("list", help="List all saved providers")
    show.set_defaults(run=list_providers)

    review = commands.add_parser("review", help="Rate and review a provider")
    review.add_argument("--provider-id", type=int, required=True, help="ID shown by the list command")
    review.add_argument("--reviewer", required=True, help="Your name")
    review.add_argument("--rating", type=int, choices=range(1, 6), required=True, help="Rating from 1 to 5")
    review.add_argument("--comment", required=True, help="Describe your experience")
    review.set_defaults(run=add_review)
    return parser


def main():
    args = build_parser().parse_args()
    try:
        args.run(args)
    except Error as error:
        print(f"Could not connect to MySQL: {error}")


if __name__ == "__main__":
    main()
