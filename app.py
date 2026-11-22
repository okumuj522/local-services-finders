"""Desktop interface for the Local Services Finder (Tkinter + MySQL)."""

import tkinter as tk
import asyncio
import math
from tkinter import messagebox, ttk
import hashlib
import hmac
import csv
import json
import os
import re
import secrets
import webbrowser
from datetime import datetime
from pathlib import Path
from tkinter import filedialog
from urllib.parse import urlencode, urlparse

from service_finder import connect
try:
    import tkintermapview
except ImportError:
    tkintermapview = None
try:
    from winrt.windows.devices.geolocation import Geolocator, GeolocationAccessStatus
except ImportError:
    Geolocator = None
    GeolocationAccessStatus = None


class ProviderCards(ttk.Frame):
    """Scrollable provider cards with a Treeview-compatible selection API."""

    def __init__(self, parent):
        super().__init__(parent)
        self.rows = {}
        self.cards = {}
        self.selected_id = None
        self.handlers = {}
        self.canvas = tk.Canvas(self, background="#eef2f7", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.pack(side="right", fill="y")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.inner = tk.Frame(self.canvas, background="#eef2f7")
        self.inner_window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind("<Configure>", lambda _event: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda event: self.canvas.itemconfigure(self.inner_window, width=event.width))
        self.placeholder = tk.Label(self.inner, text="No providers to show yet. Add a provider or adjust your search.", background="#eef2f7", foreground="#607080", font=("Segoe UI", 11), pady=28)
        self.placeholder.pack(fill="x")

    def get_children(self):
        return tuple(self.rows)

    def _on_mousewheel(self, event):
        if self.winfo_exists():
            self.canvas.yview_scroll(int(-event.delta / 120), "units")

    def delete(self, item):
        card = self.cards.pop(item, None)
        self.rows.pop(item, None)
        if card:
            card.destroy()
        if self.selected_id == item:
            self.selected_id = None
        if not self.rows and self.placeholder is None:
            self.placeholder = tk.Label(self.inner, text="No providers match this search. Try another service or location.", background="#eef2f7", foreground="#607080", font=("Segoe UI", 11), pady=28)
            self.placeholder.pack(fill="x")

    def insert(self, _parent, _index, values):
        if self.placeholder is not None:
            self.placeholder.destroy()
            self.placeholder = None
        item_id = str(values[0])
        self.rows[item_id] = tuple(values)
        name, service, location, phone, rating = values[1:6]
        distance = values[6] if len(values) > 6 else ""
        opening_hours = values[10] if len(values) > 10 else ""
        verified = bool(values[11]) if len(values) > 11 else False
        website = values[12] if len(values) > 12 else ""
        card = tk.Frame(self.inner, background="white", highlightthickness=1, highlightbackground="#dce4ee", padx=16, pady=12)
        card.pack(fill="x", padx=8, pady=5)
        tk.Label(card, text=f"{name}  ·  {service}", background="white", foreground="#1c3557", font=("Segoe UI", 12, "bold"), anchor="w").pack(fill="x")
        if verified:
            tk.Label(card, text="✓ VERIFIED", background="white", foreground="#087e78", font=("Segoe UI", 9, "bold"), anchor="w").pack(fill="x", pady=(2, 0))
        tk.Label(card, text=f"Location: {location}    |    Phone: {phone}", background="white", foreground="#475569", font=("Segoe UI", 10), anchor="w").pack(fill="x", pady=(5, 2))
        tail = f"Rating: {rating}" + (f"    ·    {distance}" if distance else "")
        tk.Label(card, text=tail, background="white", foreground="#087e78", font=("Segoe UI", 10, "bold"), anchor="w").pack(fill="x")
        if opening_hours:
            tk.Label(card, text=f"Hours: {opening_hours}", background="white", foreground="#607080", font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(3, 0))
        if website:
            tk.Label(card, text=f"Website: {website}", background="white", foreground="#476b91", font=("Segoe UI", 9), anchor="w").pack(fill="x", pady=(2, 0))
        self.cards[item_id] = card
        self._wire_card(item_id, card)
        return item_id

    def _wire_card(self, item_id, card):
        def select(_event=None):
            self.selected_id = item_id
            for key, frame in self.cards.items():
                selected = key == item_id
                frame.configure(highlightbackground="#07877f" if selected else "#dce4ee", highlightthickness=2 if selected else 1)

        for widget in (card, *card.winfo_children()):
            widget.bind("<Button-1>", select, add="+")
            for sequence, callback in self.handlers.items():
                widget.bind(sequence, callback, add="+")

    def bind(self, sequence, callback, add=None):
        self.handlers[sequence] = callback
        for card in self.cards.values():
            for widget in (card, *card.winfo_children()):
                widget.bind(sequence, callback, add="+")

    def selection(self):
        return (self.selected_id,) if self.selected_id is not None else ()

    def item(self, item_id, option):
        return self.rows.get(item_id, ()) if option == "values" else {}


class RoundButton(tk.Canvas):
    """A compact rounded button drawn with Tkinter's canvas primitives."""

    def __init__(self, parent, text, command, primary=False, width=None):
        self.label = text
        self.command = command
        self.primary = primary
        self.enabled = True
        self.base = "#087e78" if primary else "#e6edf5"
        self.hover = "#066b67" if primary else "#cfe7e5"
        self.foreground = "white" if primary else "#17365a"
        measured = max(76, len(text) * 8 + 28)
        self.button_width = width or measured
        super().__init__(parent, width=self.button_width, height=38, background=parent.winfo_toplevel().cget("background"), highlightthickness=0, cursor="hand2")
        self.bind("<Configure>", self._draw)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)
        self._draw()

    def _draw(self, _event=None):
        self.delete("all")
        width = max(self.winfo_width(), self.button_width)
        height = max(self.winfo_height(), 38)
        color = "#c8cdd3" if not self.enabled else (self.hover if getattr(self, "hovered", False) else self.base)
        radius = 14
        self.create_arc(1, 1, radius * 2, height - 1, start=90, extent=180, fill=color, outline=color)
        self.create_arc(width - radius * 2 - 1, 1, width - 1, height - 1, start=270, extent=180, fill=color, outline=color)
        self.create_rectangle(radius, 1, width - radius, height - 1, fill=color, outline=color)
        foreground = "#737b84" if not self.enabled else self.foreground
        self.create_text(width / 2, height / 2, text=self.label, fill=foreground, font=("Segoe UI", 9, "bold"))

    def _on_enter(self, _event):
        if not self.enabled:
            return
        self.hovered = True
        self._draw()

    def _on_leave(self, _event):
        self.hovered = False
        self._draw()

    def _on_click(self, _event):
        if self.enabled:
            self.command()

    def set_enabled(self, enabled):
        self.enabled = enabled
        self.configure(cursor="hand2" if enabled else "arrow")
        self._draw()

    def set_text(self, text):
        self.label = text
        self.button_width = max(self.button_width, len(text) * 8 + 28)
        self.configure(width=self.button_width)
        self._draw()


class ServiceFinderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Local Services Finder")
        self.geometry("1120x800")
        self.minsize(760, 580)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#f5f7fb")
        style.configure("TLabel", background="#f5f7fb", foreground="#24364b", font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 9, "bold"), padding=(11, 7), background="#e6edf5", foreground="#17365a", borderwidth=0)
        style.map("TButton", background=[("active", "#cfe7e5"), ("pressed", "#b8d9d6")], foreground=[("active", "#123b48")])
        style.configure("Primary.TButton", font=("Segoe UI", 9, "bold"), padding=(12, 7), background="#087e78", foreground="white")
        style.map("Primary.TButton", background=[("active", "#066b67"), ("pressed", "#055b58")], foreground=[("active", "white")])
        style.configure("TEntry", padding=6)
        style.configure("TLabelframe", background="#f5f7fb", bordercolor="#dce4ee")
        style.configure("TLabelframe.Label", background="#f5f7fb", foreground="#1c3557", font=("Segoe UI", 10, "bold"))
        self.configure(background="#f5f7fb")
        self.state("zoomed")
        self.page_canvas = tk.Canvas(self, background="#f5f7fb", highlightthickness=0)
        self.page_scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.page_canvas.yview)
        self.page_canvas.configure(yscrollcommand=self.page_scrollbar.set)
        self.page_scrollbar.pack(side="right", fill="y")
        self.page_canvas.pack(side="left", fill="both", expand=True)
        self.page = ttk.Frame(self.page_canvas, padding=16)
        self.page_window = self.page_canvas.create_window((0, 0), window=self.page, anchor="nw")
        self.page.bind("<Configure>", lambda _event: self.page_canvas.configure(scrollregion=self.page_canvas.bbox("all")))
        self.page_canvas.bind("<Configure>", lambda event: self.page_canvas.itemconfigure(self.page_window, width=event.width))
        self.bind_all("<MouseWheel>", self._route_mousewheel)
        self.is_admin = False
        self.current_coordinates = None
        self.favorites_only = False
        self.verified_only = False
        self.favorites_path = Path(os.getenv("APPDATA", str(Path.home()))) / "LocalServicesFinder" / "favorites.json"
        self.favorite_ids = self.load_favorites()
        self._build_ui()
        self.search()
        self.after(250, self.ensure_admin_setup)

    def _build_ui(self):
        header = ttk.Frame(self.page)
        header.pack(fill="x", pady=(0, 14))
        heading = ttk.Frame(header)
        heading.pack(side="left")
        ttk.Label(heading, text="Local Services Finder", font=("Segoe UI", 21, "bold"), foreground="#17365a").pack(anchor="w")
        ttk.Label(heading, text="Find trusted help in your area", foreground="#607080").pack(anchor="w", pady=(2, 0))
        self.admin_button = RoundButton(header, "Admin login", self.admin_login_or_logout)
        self.admin_button.pack(side="right", anchor="n")

        stats = ttk.Frame(self.page)
        stats.pack(fill="x", pady=(0, 12))
        self.stat_values = {}
        for key, title in (("providers", "Providers"), ("verified", "Verified"), ("reviews", "Reviews"), ("reports", "Open reports"), ("requests", "Pending requests")):
            card = tk.Frame(stats, background="white", highlightthickness=1, highlightbackground="#dce4ee", padx=13, pady=8)
            card.pack(side="left", fill="x", expand=True, padx=(0, 8))
            tk.Label(card, text=title, background="white", foreground="#607080", font=("Segoe UI", 9)).pack(anchor="w")
            value = tk.Label(card, text="—", background="white", foreground="#17365a", font=("Segoe UI", 17, "bold"))
            value.pack(anchor="w", pady=(2, 0))
            self.stat_values[key] = value

        search_frame = ttk.LabelFrame(self.page, text="Find a provider", padding=10)
        search_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(search_frame, text="Service").grid(row=0, column=0, sticky="w")
        ttk.Label(search_frame, text="Location").grid(row=0, column=1, sticky="w", padx=(8, 0))
        ttk.Label(search_frame, text="Sort by").grid(row=0, column=2, sticky="w", padx=(8, 0))
        self.service_search = ttk.Entry(search_frame, width=28)
        self.location_search = ttk.Entry(search_frame, width=28)
        self.service_search.grid(row=1, column=0, sticky="ew", pady=(3, 0))
        self.location_search.grid(row=1, column=1, sticky="ew", padx=(8, 0), pady=(3, 0))
        self.sort_mode = tk.StringVar(value="Name")
        sort_picker = ttk.Combobox(search_frame, textvariable=self.sort_mode, values=("Name", "Highest rating", "Most reviews", "Nearest"), state="readonly", width=16)
        sort_picker.grid(row=1, column=2, padx=(8, 0), pady=(3, 0))
        sort_picker.bind("<<ComboboxSelected>>", lambda _event: self.search())
        RoundButton(search_frame, "Search", self.search, primary=True).grid(row=1, column=3, padx=(8, 0))
        RoundButton(search_frame, "Show all", self.show_all).grid(row=1, column=4, padx=(6, 0))
        RoundButton(search_frame, "Use my location", self.use_my_location, primary=True).grid(row=1, column=5, padx=(6, 0))
        self.service_search.bind("<Return>", lambda _event: self.search())
        self.location_search.bind("<Return>", lambda _event: self.search())
        search_frame.columnconfigure(0, weight=1)
        search_frame.columnconfigure(1, weight=1)

        categories = ttk.Frame(self.page)
        categories.pack(fill="x", pady=(0, 8))
        ttk.Label(categories, text="Browse services:", font=("Segoe UI", 10, "bold"), foreground="#1c3557").pack(side="left", padx=(2, 8))
        for label, term in (("All", ""), ("Plumbing", "plumb"), ("Electrical", "electric"), ("Cleaning", "clean"), ("Car repair", "mechanic")):
            RoundButton(categories, label, lambda value=term: self.filter_category(value)).pack(side="left", padx=3)
        ttk.Label(categories, text="Within:", foreground="#607080").pack(side="left", padx=(14, 4))
        self.radius_limit = tk.StringVar(value="Any distance")
        radius_picker = ttk.Combobox(categories, textvariable=self.radius_limit, values=("Any distance", "5 km", "10 km", "25 km", "50 km"), state="readonly", width=13)
        radius_picker.pack(side="left")
        radius_picker.bind("<<ComboboxSelected>>", lambda _event: self.search())

        self.results = ProviderCards(self.page)
        self.results.pack(fill="both", expand=True, pady=(0, 10))
        self.results.bind("<Double-1>", lambda _event: self.view_details())

        actions = ttk.Frame(self.page)
        actions.pack(fill="x")
        admin_actions = ttk.Frame(actions)
        admin_actions.pack(fill="x", pady=(0, 4))
        RoundButton(admin_actions, "Add provider", self.add_provider_dialog, primary=True).pack(side="left")
        RoundButton(admin_actions, "Edit selected", self.edit_provider_dialog).pack(side="left", padx=6)
        RoundButton(admin_actions, "Verify selected", self.toggle_verified).pack(side="left")
        RoundButton(admin_actions, "Remove selected", self.remove_provider).pack(side="left")
        RoundButton(admin_actions, "Review reports", self.manage_reports).pack(side="left", padx=6)
        RoundButton(admin_actions, "Manage reviews", self.manage_reviews).pack(side="left")
        RoundButton(admin_actions, "Manage requests", self.manage_requests).pack(side="left", padx=6)
        RoundButton(admin_actions, "Backup / restore", self.backup_restore_menu).pack(side="left")
        public_actions = ttk.Frame(actions)
        public_actions.pack(fill="x")
        RoundButton(public_actions, "View details", self.view_details).pack(side="left")
        RoundButton(public_actions, "Contact provider", self.contact_provider, primary=True).pack(side="left", padx=6)
        RoundButton(public_actions, "Directions", self.open_directions).pack(side="left")
        RoundButton(public_actions, "Open website", self.open_provider_website).pack(side="left", padx=6)
        RoundButton(public_actions, "Request service", self.request_service, primary=True).pack(side="left")
        RoundButton(public_actions, "Track request", self.track_request).pack(side="left", padx=6)
        RoundButton(public_actions, "Write review", self.review_dialog).pack(side="left")
        RoundButton(public_actions, "Report listing", self.report_provider).pack(side="left", padx=6)
        RoundButton(public_actions, "Save favorite", self.toggle_favorite).pack(side="left")
        RoundButton(public_actions, "Favorites only", self.toggle_favorites_view).pack(side="left", padx=6)
        RoundButton(public_actions, "Verified only", self.toggle_verified_view).pack(side="left")
        self.status = ttk.Label(public_actions, text="")
        self.status.pack(side="right")

    def _route_mousewheel(self, event):
        if not hasattr(self, "results"):
            return
        widget = self.winfo_containing(event.x_root, event.y_root)
        while widget is not None:
            if widget is self.results:
                self.results.canvas.yview_scroll(int(-event.delta / 120), "units")
                return
            if widget is self.page:
                break
            widget = getattr(widget, "master", None)
        self.page_canvas.yview_scroll(int(-event.delta / 120), "units")

    def ensure_admin_setup(self):
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(*) FROM admins")
                admin_count = cursor.fetchone()[0]
                cursor.close()
            if admin_count == 0:
                messagebox.showinfo("Set up admin", "Create the first admin account to manage provider listings and reports.", parent=self)
                self.show_admin_auth(create_account=True)
        except Exception as error:
            messagebox.showerror("Admin setup unavailable", str(error), parent=self)

    def admin_login_or_logout(self):
        if self.is_admin:
            self.is_admin = False
            self.admin_button.set_text("Admin login")
            self.status.config(text="Logged out")
            return
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(*) FROM admins")
                create_account = cursor.fetchone()[0] == 0
                cursor.close()
        except Exception as error:
            messagebox.showerror("Admin login unavailable", str(error), parent=self)
            return
        self.show_admin_auth(create_account=create_account)

    def show_admin_auth(self, create_account=False):
        self.auth_success = False
        window = tk.Toplevel(self)
        window.title("Create admin account" if create_account else "Admin login")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Create the first admin account" if create_account else "Admin login", font=("Segoe UI", 12, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="Username").grid(row=1, column=0, sticky="w", pady=3)
        username = ttk.Entry(frame, width=32)
        username.grid(row=1, column=1, pady=3)
        ttk.Label(frame, text="Password").grid(row=2, column=0, sticky="w", pady=3)
        password = ttk.Entry(frame, width=32, show="*")
        password.grid(row=2, column=1, pady=3)
        confirm = None
        if create_account:
            ttk.Label(frame, text="Confirm password").grid(row=3, column=0, sticky="w", pady=3)
            confirm = ttk.Entry(frame, width=32, show="*")
            confirm.grid(row=3, column=1, pady=3)

        def submit():
            user = username.get().strip()
            secret = password.get()
            if not user or not secret:
                messagebox.showwarning("Missing information", "Enter a username and password.", parent=window)
                return
            if create_account and len(secret) < 10:
                messagebox.showwarning("Password too short", "Use a password with at least 10 characters.", parent=window)
                return
            if create_account and secret != confirm.get():
                messagebox.showwarning("Passwords do not match", "Enter the same password in both fields.", parent=window)
                return
            try:
                with connect() as db:
                    cursor = db.cursor()
                    if create_account:
                        salt = secrets.token_bytes(16)
                        digest = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 600_000)
                        cursor.execute(
                            "INSERT INTO admins (username, password_salt, password_hash) VALUES (%s, %s, %s)",
                            (user, salt.hex(), digest.hex()),
                        )
                        db.commit()
                        self.auth_success = True
                    else:
                        cursor.execute("SELECT password_salt, password_hash FROM admins WHERE username = %s", (user,))
                        record = cursor.fetchone()
                        if record:
                            salt = bytes.fromhex(record[0])
                            expected = hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, 600_000).hex()
                            self.auth_success = hmac.compare_digest(expected, record[1])
                    cursor.close()
                if not self.auth_success:
                    messagebox.showerror("Login failed", "The username or password is incorrect.", parent=window)
                    return
                self.is_admin = True
                self.admin_button.set_text("Log out admin")
                self.status.config(text=f"Admin: {user}")
                window.destroy()
            except Exception as error:
                messagebox.showerror("Could not sign in", str(error), parent=window)

        RoundButton(frame, "Create account" if create_account else "Log in", submit, primary=True).grid(row=4 if create_account else 3, column=1, sticky="e", pady=(8, 0))
        username.focus_set()
        self.wait_window(window)
        return self.auth_success

    def require_admin(self):
        if self.is_admin:
            return True
        messagebox.showinfo("Admin login required", "Log in as an admin to manage provider listings and reports.", parent=self)
        self.show_admin_auth()
        return self.is_admin

    def search(self):
        nearest = self.sort_mode.get() == "Nearest" and self.current_coordinates is not None
        radius_text = self.radius_limit.get()
        radius_km = float(radius_text.split()[0]) if radius_text != "Any distance" else None
        if radius_km is not None and self.current_coordinates is None:
            self.status.config(text="Choose Use my location before setting a distance limit")
            return
        sort_order = {
            "Name": "p.name ASC",
            "Highest rating": "average_rating DESC, review_count DESC, p.name ASC",
            "Most reviews": "review_count DESC, average_rating DESC, p.name ASC",
            "Nearest": "p.name ASC",
        }.get(self.sort_mode.get(), "p.name ASC")
        for item in self.results.get_children():
            self.results.delete(item)
        try:
            with connect() as db:
                cursor = db.cursor(dictionary=True)
                cursor.execute(
                    """SELECT p.*, COUNT(r.id) AS review_count, AVG(r.rating) AS average_rating
                       FROM providers p LEFT JOIN reviews r ON r.provider_id = p.id
                       WHERE p.service LIKE %s AND p.location LIKE %s
                       GROUP BY p.id ORDER BY """ + sort_order,
                    (f"%{self.service_search.get().strip()}%", f"%{self.location_search.get().strip()}%"),
                )
                rows = cursor.fetchall()
                cursor.close()
            if self.current_coordinates is not None and (nearest or radius_km is not None):
                for row in rows:
                    row["distance_km"] = self.distance_km(
                        self.current_coordinates[0], self.current_coordinates[1], row["latitude"], row["longitude"]
                    )
            if nearest:
                rows.sort(key=lambda row: row["distance_km"] if row["distance_km"] is not None else float("inf"))
            if radius_km is not None:
                rows = [row for row in rows if row.get("distance_km") is not None and row["distance_km"] <= radius_km]
            if self.verified_only:
                rows = [row for row in rows if row["verified"]]
            if self.favorites_only:
                rows = [row for row in rows if row["id"] in self.favorite_ids]
            for row in rows:
                rating = f"{row['average_rating']:.1f}/5 ({row['review_count']})" if row["review_count"] else "No reviews"
                distance = f"{row['distance_km']:.1f} km away" if row.get("distance_km") is not None else ""
                favorite_label = "★ Saved" if row["id"] in self.favorite_ids else ""
                self.results.insert("", "end", values=(row["id"], row["name"], row["service"], row["location"], row["phone"], rating, distance, row["latitude"], row["longitude"], favorite_label, row["opening_hours"], row["verified"], row["website"]))
            if nearest:
                located_count = sum(row.get("distance_km") is not None for row in rows)
                self.status.config(text=f"Nearest · {located_count} provider(s) have map coordinates")
            else:
                self.status.config(text=f"{len(rows)} provider(s)")
            self.refresh_stats()
        except Exception as error:
            messagebox.showerror("Could not load providers", f"Check that MySQL is running and your settings are correct.\n\n{error}")

    def refresh_stats(self):
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute(
                    """SELECT (SELECT COUNT(*) FROM providers),
                              (SELECT COUNT(*) FROM providers WHERE verified = 1),
                              (SELECT COUNT(*) FROM reviews),
                              (SELECT COUNT(*) FROM provider_reports WHERE status = 'open'),
                              (SELECT COUNT(*) FROM service_requests WHERE status = 'pending')"""
                )
                counts = cursor.fetchone()
                cursor.close()
            for key, value in zip(("providers", "verified", "reviews", "reports", "requests"), counts):
                self.stat_values[key].config(text=str(value))
        except Exception:
            pass

    @staticmethod
    def distance_km(lat1, lon1, lat2, lon2):
        if lat2 is None or lon2 is None:
            return None
        radius = 6371.0
        lat1, lon1, lat2, lon2 = map(math.radians, (float(lat1), float(lon1), float(lat2), float(lon2)))
        delta_lat, delta_lon = lat2 - lat1, lon2 - lon1
        value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
        return radius * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))

    def use_my_location(self):
        if Geolocator is None:
            messagebox.showinfo("Location feature not installed", "In PowerShell, run: python -m pip install -r requirements.txt", parent=self)
            return
        try:
            async def request_access():
                return await Geolocator.request_access_async()

            status = asyncio.run(request_access())
            if status != GeolocationAccessStatus.ALLOWED:
                messagebox.showinfo("Location unavailable", "Allow location access in Windows Settings, or continue searching by neighborhood.", parent=self)
                return

            async def get_position():
                return await Geolocator().get_geoposition_async()

            position = asyncio.run(get_position())
            point = position.coordinate.point.position
            self.current_coordinates = (point.latitude, point.longitude)
            self.sort_mode.set("Nearest")
            self.location_search.delete(0, "end")
            self.status.config(text="Getting nearby providers…")
            self.search()
            with connect() as db:
                cursor = db.cursor()
                cursor.execute("SELECT COUNT(*) FROM providers WHERE latitude IS NOT NULL AND longitude IS NOT NULL")
                located_count = cursor.fetchone()[0]
                cursor.close()
            if located_count == 0:
                messagebox.showinfo(
                    "Location ready",
                    "Your location is ready. Add latitude and longitude to provider listings to see distance from you. Select a provider, choose Edit selected, and enter its map coordinates.",
                    parent=self,
                )
            else:
                self.status.config(text=f"Using your location · {located_count} provider(s) have map coordinates")
        except Exception as error:
            messagebox.showerror("Could not get location", f"Turn on Windows Location services, or search by neighborhood.\n\n{error}", parent=self)

    def show_all(self):
        self.favorites_only = False
        self.verified_only = False
        self.radius_limit.set("Any distance")
        self.service_search.delete(0, "end")
        self.location_search.delete(0, "end")
        self.search()

    def filter_category(self, term):
        self.service_search.delete(0, "end")
        self.service_search.insert(0, term)
        self.search()

    def load_favorites(self):
        try:
            saved = json.loads(self.favorites_path.read_text(encoding="utf-8"))
            return {int(provider_id) for provider_id in saved}
        except (OSError, ValueError, TypeError):
            return set()

    def toggle_favorite(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider card first.", parent=self)
            return
        provider_id = int(self.results.item(selected[0], "values")[0])
        values = self.results.item(selected[0], "values")
        provider_name = values[1]
        if provider_id in self.favorite_ids:
            self.favorite_ids.remove(provider_id)
            message = f"Removed {provider_name} from favorites."
        else:
            self.favorite_ids.add(provider_id)
            message = f"Saved {provider_name} to favorites."
        try:
            self.favorites_path.parent.mkdir(parents=True, exist_ok=True)
            self.favorites_path.write_text(json.dumps(sorted(self.favorite_ids)), encoding="utf-8")
            self.status.config(text=message)
            self.search()
        except OSError as error:
            messagebox.showerror("Could not save favorite", str(error), parent=self)

    def toggle_favorites_view(self):
        self.favorites_only = not self.favorites_only
        self.search()
        self.status.config(text="Showing favorites" if self.favorites_only else "Showing all providers")

    def toggle_verified_view(self):
        self.verified_only = not self.verified_only
        self.search()
        self.status.config(text="Showing verified providers" if self.verified_only else "Showing all providers")

    def add_provider_dialog(self):
        if not self.require_admin():
            return
        self._form_dialog("Add provider", ["Name", "Service", "Location", "Phone", "Price (optional)", "Notes (optional)", "Latitude (optional)", "Longitude (optional)", "Opening hours (optional)", "Website (optional)"], self._save_provider)

    def _save_provider(self, values, window):
        name, service, location, phone, price, notes, latitude, longitude, opening_hours, website = values
        if not self.validate_provider(name, service, location, phone, latitude, longitude, window):
            return
        latitude, longitude = self.parse_coordinates(latitude, longitude, window)
        if latitude is False:
            return
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute(
                    "INSERT INTO providers (name, service, location, phone, price, notes, latitude, longitude, opening_hours, website) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (name, service, location, phone, price, notes, latitude, longitude, opening_hours, website),
                )
                db.commit()
                cursor.close()
            window.destroy()
            self.show_all()
            messagebox.showinfo("Provider saved", f"{name} was saved. The list below shows providers in your MySQL database.", parent=self)
            self.search()
        except Exception as error:
            messagebox.showerror("Could not add provider", str(error), parent=window)

    def review_dialog(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider in the list first.")
            return
        values = self.results.item(selected[0], "values")
        provider_id, provider_name = int(values[0]), values[1]
        window = tk.Toplevel(self)
        window.title(f"Review {provider_name}")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Review for {provider_name}").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="Your name").grid(row=1, column=0, sticky="w")
        reviewer = ttk.Entry(frame, width=36)
        reviewer.grid(row=1, column=1, pady=3)
        ttk.Label(frame, text="Rating (1–5)").grid(row=2, column=0, sticky="w")
        rating = ttk.Spinbox(frame, from_=1, to=5, width=5)
        rating.set(5)
        rating.grid(row=2, column=1, sticky="w", pady=3)
        ttk.Label(frame, text="Your experience").grid(row=3, column=0, sticky="nw")
        comment = tk.Text(frame, width=36, height=5, wrap="word")
        comment.grid(row=3, column=1, pady=3)

        def save():
            text = comment.get("1.0", "end").strip()
            if not reviewer.get().strip() or not text:
                messagebox.showwarning("Missing information", "Enter your name and a review.", parent=window)
                return
            try:
                with connect() as db:
                    cursor = db.cursor()
                    cursor.execute(
                        "INSERT INTO reviews (provider_id, reviewer, rating, comment) VALUES (%s, %s, %s, %s)",
                        (provider_id, reviewer.get().strip(), int(rating.get()), text),
                    )
                    db.commit()
                    cursor.close()
                window.destroy()
                self.search()
            except Exception as error:
                messagebox.showerror("Could not save review", str(error), parent=window)

        RoundButton(frame, "Save review", save, primary=True).grid(row=4, column=1, sticky="e", pady=(8, 0))

    def contact_provider(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider in the list first.")
            return
        values = self.results.item(selected[0], "values")
        name, phone = values[1], values[4]
        window = tk.Toplevel(self)
        window.title(f"Contact {name}")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Contact {name}", font=("Segoe UI", 13, "bold")).pack(anchor="w")
        ttk.Label(frame, text=phone, font=("Segoe UI", 16)).pack(anchor="w", pady=10)

        def copy_number(show_message=True):
            self.clipboard_clear()
            self.clipboard_append(phone)
            self.update()
            if show_message:
                messagebox.showinfo("Copied", "The phone number is copied to your clipboard.", parent=window)

        def open_phone():
            phone_link = re.sub(r"[^0-9+]", "", phone)
            try:
                opened = webbrowser.open(f"tel:{phone_link}")
            except Exception:
                opened = False
            if not opened:
                copy_number(show_message=False)
                messagebox.showinfo("Phone app unavailable", "Your computer could not open a phone app, so the number was copied instead.", parent=window)

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="e")
        RoundButton(buttons, "Copy number", copy_number).pack(side="left", padx=(0, 8))
        RoundButton(buttons, "Open phone app", open_phone, primary=True).pack(side="left")

    def request_service(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider card first.")
            return
        provider_values = self.results.item(selected[0], "values")
        provider_id, provider_name = int(provider_values[0]), provider_values[1]
        window = tk.Toplevel(self)
        window.title(f"Request service from {provider_name}")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Request service from {provider_name}", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="Your name").grid(row=1, column=0, sticky="w", pady=3)
        name = ttk.Entry(frame, width=38)
        name.grid(row=1, column=1, pady=3)
        ttk.Label(frame, text="Phone number").grid(row=2, column=0, sticky="w", pady=3)
        phone = ttk.Entry(frame, width=38)
        phone.grid(row=2, column=1, pady=3)
        ttk.Label(frame, text="Preferred date/time").grid(row=3, column=0, sticky="w", pady=3)
        preferred = ttk.Entry(frame, width=38)
        preferred.grid(row=3, column=1, pady=3)
        ttk.Label(frame, text="What do you need?").grid(row=4, column=0, sticky="nw", pady=3)
        description = tk.Text(frame, width=38, height=5, wrap="word")
        description.grid(row=4, column=1, pady=3)

        def submit():
            requester_name, requester_phone = name.get().strip(), phone.get().strip()
            when, details = preferred.get().strip(), description.get("1.0", "end").strip()
            if not all((requester_name, requester_phone, when, details)):
                messagebox.showwarning("Missing information", "Complete all fields before sending the request.", parent=window)
                return
            if not 7 <= sum(char.isdigit() for char in requester_phone) <= 15:
                messagebox.showwarning("Check phone number", "Enter a phone number with 7 to 15 digits.", parent=window)
                return
            try:
                tracking_code = f"LSF-{secrets.token_hex(4).upper()}"
                with connect() as db:
                    cursor = db.cursor()
                    cursor.execute(
                        "INSERT INTO service_requests (tracking_code, provider_id, requester_name, phone, preferred_time, description) VALUES (%s, %s, %s, %s, %s, %s)",
                        (tracking_code, provider_id, requester_name, requester_phone, when, details),
                    )
                    db.commit()
                    cursor.close()
                window.destroy()
                self.refresh_stats()
                messagebox.showinfo("Request sent", f"Your request to {provider_name} has been saved. Keep this tracking code to check its status later:\n\n{tracking_code}", parent=self)
            except Exception as error:
                messagebox.showerror("Could not send request", str(error), parent=window)

        RoundButton(frame, "Send request", submit, primary=True).grid(row=5, column=1, sticky="e", pady=(8, 0))

    def track_request(self):
        window = tk.Toplevel(self)
        window.title("Track service request")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Enter your tracking code and phone number.").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="Tracking code").grid(row=1, column=0, sticky="w", pady=3)
        code = ttk.Entry(frame, width=36)
        code.grid(row=1, column=1, pady=3)
        ttk.Label(frame, text="Phone number").grid(row=2, column=0, sticky="w", pady=3)
        phone = ttk.Entry(frame, width=36)
        phone.grid(row=2, column=1, pady=3)
        result = ttk.Label(frame, text="", wraplength=380, justify="left")
        result.grid(row=4, column=0, columnspan=2, sticky="w", pady=(10, 0))

        def lookup():
            try:
                with connect() as db:
                    cursor = db.cursor(dictionary=True)
                    cursor.execute(
                        """SELECT r.id, p.name AS provider, r.preferred_time, r.status, r.admin_response
                           FROM service_requests r JOIN providers p ON p.id = r.provider_id
                           WHERE r.tracking_code = %s AND r.phone = %s""",
                        (code.get().strip().upper(), phone.get().strip()),
                    )
                    request = cursor.fetchone()
                    cursor.close()
                if request:
                    answer = request["admin_response"] or "No admin reply yet."
                    result.config(text=f"Provider: {request['provider']}\nPreferred time: {request['preferred_time']}\nStatus: {request['status'].title()}\nAdmin reply: {answer}")
                    cancel_button.set_enabled(request["status"] == "pending")
                else:
                    result.config(text="No request matched that code and phone number.")
                    cancel_button.set_enabled(False)
            except Exception as error:
                messagebox.showerror("Could not check request", str(error), parent=window)

        def cancel_request():
            tracking_code = code.get().strip().upper()
            requester_phone = phone.get().strip()
            if not tracking_code or not requester_phone:
                messagebox.showinfo("Enter request details", "Enter the tracking code and phone number, then check the status first.", parent=window)
                return
            if not messagebox.askyesno("Cancel request", "Cancel this pending service request? This cannot be undone.", parent=window):
                return
            try:
                with connect() as db:
                    cursor = db.cursor()
                    cursor.execute(
                        "UPDATE service_requests SET status = 'cancelled' WHERE tracking_code = %s AND phone = %s AND status = 'pending'",
                        (tracking_code, requester_phone),
                    )
                    changed = cursor.rowcount
                    db.commit()
                    cursor.close()
                if changed:
                    messagebox.showinfo("Request cancelled", "Your request has been cancelled.", parent=window)
                else:
                    messagebox.showinfo("Could not cancel", "This request may no longer be pending. Check its latest status.", parent=window)
                lookup()
            except Exception as error:
                messagebox.showerror("Could not cancel request", str(error), parent=window)

        RoundButton(frame, "Check status", lookup, primary=True).grid(row=3, column=1, sticky="e", pady=(6, 0))
        cancel_button = RoundButton(frame, "Cancel pending request", cancel_request)
        cancel_button.grid(row=5, column=1, sticky="e", pady=(8, 0))
        cancel_button.set_enabled(False)

    def open_directions(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider in the list first.")
            return
        values = self.results.item(selected[0], "values")
        latitude, longitude = values[7], values[8]
        if latitude in (None, "") or longitude in (None, ""):
            messagebox.showinfo("Map coordinates needed", "This provider has no map coordinates yet. An admin can add them with Edit selected.")
            return
        route = {"api": "1", "destination": f"{latitude},{longitude}"}
        if self.current_coordinates:
            route["origin"] = f"{self.current_coordinates[0]},{self.current_coordinates[1]}"
        webbrowser.open("https://www.google.com/maps/dir/?" + urlencode(route))

    def open_provider_website(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider card first.")
            return
        values = self.results.item(selected[0], "values")
        website = values[12] if len(values) > 12 else ""
        if not website:
            messagebox.showinfo("No website listed", "This provider has not added a website.")
            return
        if not urlparse(website).scheme:
            website = "https://" + website
        if urlparse(website).scheme not in ("http", "https"):
            messagebox.showwarning("Invalid website", "The provider website must start with http:// or https://")
            return
        webbrowser.open(website)

    def report_provider(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider in the list first.")
            return
        values = self.results.item(selected[0], "values")
        provider_id, provider_name = int(values[0]), values[1]
        window = tk.Toplevel(self)
        window.title(f"Report {provider_name}")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Report a problem with {provider_name}", font=("Segoe UI", 11, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))
        ttk.Label(frame, text="Your name").grid(row=1, column=0, sticky="w")
        reporter = ttk.Entry(frame, width=38)
        reporter.grid(row=1, column=1, pady=3)
        ttk.Label(frame, text="Problem").grid(row=2, column=0, sticky="w")
        issue = ttk.Combobox(frame, values=("Wrong phone number", "Wrong service or location", "Provider no longer available", "Other"), state="readonly", width=35)
        issue.current(0)
        issue.grid(row=2, column=1, pady=3)
        ttk.Label(frame, text="Details").grid(row=3, column=0, sticky="nw")
        details = tk.Text(frame, width=38, height=5, wrap="word")
        details.grid(row=3, column=1, pady=3)

        def submit():
            reporter_name = reporter.get().strip()
            detail_text = details.get("1.0", "end").strip()
            if not reporter_name or not detail_text:
                messagebox.showwarning("Missing information", "Enter your name and explain the problem.", parent=window)
                return
            try:
                with connect() as db:
                    cursor = db.cursor()
                    cursor.execute(
                        "INSERT INTO provider_reports (provider_id, reporter, issue, details) VALUES (%s, %s, %s, %s)",
                        (provider_id, reporter_name, issue.get(), detail_text),
                    )
                    db.commit()
                    cursor.close()
                window.destroy()
                messagebox.showinfo("Report saved", "Thank you. The report is saved for review.", parent=self)
            except Exception as error:
                messagebox.showerror("Could not save report", str(error), parent=window)

        RoundButton(frame, "Submit report", submit, primary=True).grid(row=4, column=1, sticky="e", pady=(8, 0))

    def manage_reports(self):
        if not self.require_admin():
            return
        window = tk.Toplevel(self)
        window.title("Provider reports")
        window.geometry("760x400")
        window.transient(self)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        columns = ("id", "provider", "issue", "reporter", "date", "status")
        reports = ttk.Treeview(frame, columns=columns, show="headings")
        for key, label, width in (("id", "ID", 45), ("provider", "Provider", 150), ("issue", "Issue", 170), ("reporter", "Reported by", 110), ("date", "Date", 130), ("status", "Status", 80)):
            reports.heading(key, text=label)
            reports.column(key, width=width, anchor="w")
        reports.pack(fill="both", expand=True)
        detail = tk.Text(frame, height=4, wrap="word", state="disabled")
        detail.pack(fill="x", pady=(8, 6))
        ttk.Label(frame, text="Reply shown to customer").pack(anchor="w")
        admin_reply = tk.Text(frame, height=3, wrap="word")
        admin_reply.pack(fill="x", pady=(3, 6))

        def refresh_reports():
            reports.delete(*reports.get_children())
            try:
                with connect() as db:
                    cursor = db.cursor(dictionary=True)
                    cursor.execute(
                        """SELECT r.id, p.name AS provider, r.issue, r.reporter, r.created_at, r.status, r.details
                           FROM provider_reports r JOIN providers p ON p.id = r.provider_id
                           ORDER BY (r.status = 'open') DESC, r.created_at DESC"""
                    )
                    rows = cursor.fetchall()
                    cursor.close()
                for row in rows:
                    reports.insert("", "end", values=(row["id"], row["provider"], row["issue"], row["reporter"], row["created_at"], row["status"]), tags=(row["details"],))
            except Exception as error:
                messagebox.showerror("Could not load reports", str(error), parent=window)

        def show_detail(_event=None):
            selection = reports.selection()
            if not selection:
                return
            value = reports.item(selection[0], "tags")[0]
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", value)
            detail.configure(state="disabled")

        def mark_resolved():
            selection = reports.selection()
            if not selection:
                messagebox.showinfo("Select a report", "Choose a report first.", parent=window)
                return
            report_id = int(reports.item(selection[0], "values")[0])
            try:
                with connect() as db:
                    cursor = db.cursor()
                    cursor.execute("UPDATE provider_reports SET status = 'resolved' WHERE id = %s", (report_id,))
                    db.commit()
                    cursor.close()
                refresh_reports()
            except Exception as error:
                messagebox.showerror("Could not update report", str(error), parent=window)

        reports.bind("<<TreeviewSelect>>", show_detail)
        RoundButton(frame, "Mark resolved", mark_resolved, primary=True).pack(anchor="e")
        refresh_reports()

    def manage_reviews(self):
        if not self.require_admin():
            return
        window = tk.Toplevel(self)
        window.title("Manage reviews")
        window.geometry("780x440")
        window.transient(self)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        columns = ("id", "provider", "reviewer", "rating", "date")
        reviews = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        for column, title, width in (("id", "ID", 48), ("provider", "Provider", 180), ("reviewer", "Reviewer", 130), ("rating", "Rating", 70), ("date", "Date", 150)):
            reviews.heading(column, text=title)
            reviews.column(column, width=width, anchor="w")
        reviews.pack(fill="both", expand=True)
        comment_box = tk.Text(frame, height=5, wrap="word", state="disabled")
        comment_box.pack(fill="x", pady=(8, 6))
        review_comments = {}

        def refresh():
            reviews.delete(*reviews.get_children())
            review_comments.clear()
            try:
                with connect() as db:
                    cursor = db.cursor(dictionary=True)
                    cursor.execute(
                        """SELECT r.id, p.name AS provider, r.reviewer, r.rating, r.created_at, r.comment
                           FROM reviews r JOIN providers p ON p.id = r.provider_id ORDER BY r.created_at DESC"""
                    )
                    rows = cursor.fetchall()
                    cursor.close()
                for row in rows:
                    key = str(row["id"])
                    reviews.insert("", "end", iid=key, values=(row["id"], row["provider"], row["reviewer"], row["rating"], row["created_at"]))
                    review_comments[key] = row["comment"]
            except Exception as error:
                messagebox.showerror("Could not load reviews", str(error), parent=window)

        def show_comment(_event=None):
            selection = reviews.selection()
            comment_box.configure(state="normal")
            comment_box.delete("1.0", "end")
            if selection:
                comment_box.insert("1.0", review_comments.get(selection[0], ""))
            comment_box.configure(state="disabled")

        def delete_review():
            selection = reviews.selection()
            if not selection:
                messagebox.showinfo("Select a review", "Choose a review first.", parent=window)
                return
            review_id = int(selection[0])
            if not messagebox.askyesno("Remove review", "Permanently remove this review?", icon="warning", parent=window):
                return
            try:
                with connect() as db:
                    cursor = db.cursor()
                    cursor.execute("DELETE FROM reviews WHERE id = %s", (review_id,))
                    db.commit()
                    cursor.close()
                refresh()
                self.search()
            except Exception as error:
                messagebox.showerror("Could not remove review", str(error), parent=window)

        reviews.bind("<<TreeviewSelect>>", show_comment)
        RoundButton(frame, "Remove selected review", delete_review, primary=True).pack(anchor="e")
        refresh()

    def manage_requests(self):
        if not self.require_admin():
            return
        window = tk.Toplevel(self)
        window.title("Service requests")
        window.geometry("860x500")
        window.transient(self)
        frame = ttk.Frame(window, padding=12)
        frame.pack(fill="both", expand=True)
        columns = ("code", "provider", "requester", "phone", "preferred", "status")
        tree = ttk.Treeview(frame, columns=columns, show="headings", height=12)
        for col, title, width in (("code", "Tracking code", 120), ("provider", "Provider", 150), ("requester", "Customer", 130), ("phone", "Phone", 110), ("preferred", "Preferred time", 160), ("status", "Status", 90)):
            tree.heading(col, text=title)
            tree.column(col, width=width, anchor="w")
        tree.pack(fill="both", expand=True)
        detail = tk.Text(frame, height=4, wrap="word", state="disabled")
        detail.pack(fill="x", pady=(8, 6))
        status = ttk.Combobox(frame, values=("pending", "accepted", "declined", "completed", "cancelled"), state="readonly", width=15)
        status.set("pending")
        status.pack(side="left")
        descriptions = {}

        def refresh():
            tree.delete(*tree.get_children())
            descriptions.clear()
            try:
                with connect() as db:
                    cursor = db.cursor(dictionary=True)
                    cursor.execute(
                        """SELECT r.id, r.tracking_code, p.name AS provider, r.requester_name, r.phone, r.preferred_time, r.status, r.description, r.admin_response
                           FROM service_requests r JOIN providers p ON p.id = r.provider_id
                           ORDER BY (r.status = 'pending') DESC, r.created_at DESC"""
                    )
                    rows = cursor.fetchall()
                    cursor.close()
                for row in rows:
                    key = str(row["id"])
                    tree.insert("", "end", iid=key, values=(row["tracking_code"], row["provider"], row["requester_name"], row["phone"], row["preferred_time"], row["status"]))
                    descriptions[key] = {"description": row["description"], "admin_response": row["admin_response"] or ""}
            except Exception as error:
                messagebox.showerror("Could not load requests", str(error), parent=window)

        def select_request(_event=None):
            selected = tree.selection()
            if not selected:
                return
            detail.configure(state="normal")
            detail.delete("1.0", "end")
            detail.insert("1.0", descriptions.get(selected[0], {}).get("description", ""))
            detail.configure(state="disabled")
            status.set(tree.item(selected[0], "values")[5])
            admin_reply.delete("1.0", "end")
            admin_reply.insert("1.0", descriptions.get(selected[0], {}).get("admin_response", ""))

        def save_status():
            selected = tree.selection()
            if not selected:
                messagebox.showinfo("Select a request", "Choose a request first.", parent=window)
                return
            try:
                with connect() as db:
                    cursor = db.cursor()
                    cursor.execute("UPDATE service_requests SET status = %s, admin_response = %s WHERE id = %s", (status.get(), admin_reply.get("1.0", "end").strip(), int(selected[0])))
                    db.commit()
                    cursor.close()
                refresh()
                self.refresh_stats()
            except Exception as error:
                messagebox.showerror("Could not update request", str(error), parent=window)

        tree.bind("<<TreeviewSelect>>", select_request)
        RoundButton(frame, "Save status", save_status, primary=True).pack(anchor="e")
        refresh()

    def backup_restore_menu(self):
        if not self.require_admin():
            return
        window = tk.Toplevel(self)
        window.title("Database backup")
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Back up or restore directory data", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        ttk.Label(frame, text="Backups include providers, reviews, and reports. Admin accounts are excluded.", wraplength=420).pack(anchor="w", pady=(4, 12))
        RoundButton(frame, "Export backup and CSV files", lambda: self.export_backup(window), primary=True).pack(fill="x", pady=3)
        RoundButton(frame, "Restore from JSON backup", lambda: self.restore_backup(window)).pack(fill="x", pady=3)

    def export_backup(self, parent):
        folder = filedialog.askdirectory(parent=parent, title="Choose a folder for the backup")
        if not folder:
            return
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        try:
            with connect() as db:
                cursor = db.cursor(dictionary=True)
                cursor.execute("SELECT id, name, service, location, phone, price, notes, latitude, longitude, opening_hours, verified, website FROM providers ORDER BY id")
                providers = cursor.fetchall()
                cursor.execute("SELECT id, provider_id, reviewer, rating, comment, created_at FROM reviews ORDER BY id")
                reviews = cursor.fetchall()
                cursor.execute("SELECT id, provider_id, reporter, issue, details, status, created_at FROM provider_reports ORDER BY id")
                reports = cursor.fetchall()
                cursor.execute("SELECT id, tracking_code, provider_id, requester_name, phone, preferred_time, description, admin_response, status, created_at FROM service_requests ORDER BY id")
                requests = cursor.fetchall()
                cursor.close()
            payload = {
                "format": "local-services-finder-backup",
                "version": 1,
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "providers": providers,
                "reviews": reviews,
                "provider_reports": reports,
                "service_requests": requests,
            }
            output_dir = Path(folder)
            (output_dir / f"local_services_backup_{timestamp}.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
            )
            empty_headers = {
                "providers": ["id", "name", "service", "location", "phone", "price", "notes", "latitude", "longitude", "opening_hours", "verified", "website"],
                "reviews": ["id", "provider_id", "reviewer", "rating", "comment", "created_at"],
                "reports": ["id", "provider_id", "reporter", "issue", "details", "status", "created_at"],
                "requests": ["id", "tracking_code", "provider_id", "requester_name", "phone", "preferred_time", "description", "admin_response", "status", "created_at"],
            }
            for name, rows in (("providers", providers), ("reviews", reviews), ("reports", reports), ("requests", requests)):
                path = output_dir / f"local_services_{name}_{timestamp}.csv"
                fields = list(rows[0].keys()) if rows else empty_headers[name]
                with path.open("w", newline="", encoding="utf-8-sig") as output:
                    writer = csv.DictWriter(output, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            messagebox.showinfo("Backup created", f"Backup and CSV files were saved to:\n{output_dir}", parent=parent)
        except Exception as error:
            messagebox.showerror("Backup failed", str(error), parent=parent)

    def restore_backup(self, parent):
        filename = filedialog.askopenfilename(
            parent=parent,
            title="Select a Local Services Finder JSON backup",
            filetypes=(("JSON backup", "*.json"), ("All files", "*.*")),
        )
        if not filename:
            return
        try:
            payload = json.loads(Path(filename).read_text(encoding="utf-8"))
            if payload.get("format") != "local-services-finder-backup" or payload.get("version") != 1:
                raise ValueError("This file is not a supported Local Services Finder backup.")
            providers, reviews, reports = payload["providers"], payload["reviews"], payload["provider_reports"]
            requests = payload.get("service_requests", [])
            if not all(isinstance(rows, list) for rows in (providers, reviews, reports, requests)):
                raise ValueError("The backup data is incomplete.")
            needed = (
                ({"id", "name", "service", "location", "phone", "price", "notes", "latitude", "longitude"}, providers),
                ({"id", "provider_id", "reviewer", "rating", "comment", "created_at"}, reviews),
                ({"id", "provider_id", "reporter", "issue", "details", "status", "created_at"}, reports),
                ({"id", "provider_id", "requester_name", "phone", "preferred_time", "description", "status", "created_at"}, requests),
            )
            if any(any(not required.issubset(row) for row in rows) for required, rows in needed):
                raise ValueError("The backup contains an incomplete record.")
        except Exception as error:
            messagebox.showerror("Could not read backup", str(error), parent=parent)
            return
        if not messagebox.askyesno(
            "Restore backup",
            "Restore this backup into the current database? Restore is allowed only when the provider, review, and report tables are empty.",
            icon="warning",
            parent=parent,
        ):
            return
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute("SELECT (SELECT COUNT(*) FROM providers) + (SELECT COUNT(*) FROM reviews) + (SELECT COUNT(*) FROM provider_reports) + (SELECT COUNT(*) FROM service_requests)")
                if cursor.fetchone()[0]:
                    cursor.close()
                    messagebox.showerror("Database is not empty", "Restore stopped to protect existing records. Choose an empty database.", parent=parent)
                    return
                cursor.executemany(
                    "INSERT INTO providers (id, name, service, location, phone, price, notes, latitude, longitude, opening_hours, verified, website) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [(r["id"], r["name"], r["service"], r["location"], r["phone"], r["price"], r["notes"], r["latitude"], r["longitude"], r.get("opening_hours"), r.get("verified", 0), r.get("website")) for r in providers],
                )
                cursor.executemany(
                    "INSERT INTO reviews (id, provider_id, reviewer, rating, comment, created_at) VALUES (%s, %s, %s, %s, %s, %s)",
                    [(r["id"], r["provider_id"], r["reviewer"], r["rating"], r["comment"], r["created_at"]) for r in reviews],
                )
                cursor.executemany(
                    "INSERT INTO provider_reports (id, provider_id, reporter, issue, details, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                    [(r["id"], r["provider_id"], r["reporter"], r["issue"], r["details"], r["status"], r["created_at"]) for r in reports],
                )
                cursor.executemany(
                    "INSERT INTO service_requests (id, tracking_code, provider_id, requester_name, phone, preferred_time, description, admin_response, status, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    [(r["id"], r.get("tracking_code"), r["provider_id"], r["requester_name"], r["phone"], r["preferred_time"], r["description"], r.get("admin_response"), r["status"], r["created_at"]) for r in requests],
                )
                db.commit()
                cursor.close()
            parent.destroy()
            self.show_all()
            messagebox.showinfo("Restore complete", f"Restored {len(providers)} providers, {len(reviews)} reviews, {len(reports)} reports, and {len(requests)} service requests.", parent=self)
        except Exception as error:
            messagebox.showerror("Restore failed", f"The restore could not be completed.\n\n{error}", parent=parent)

    def edit_provider_dialog(self):
        if not self.require_admin():
            return
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider in the list first.")
            return
        provider_id = int(self.results.item(selected[0], "values")[0])
        try:
            with connect() as db:
                cursor = db.cursor(dictionary=True)
                cursor.execute("SELECT * FROM providers WHERE id = %s", (provider_id,))
                provider = cursor.fetchone()
                cursor.close()
        except Exception as error:
            messagebox.showerror("Could not load provider", str(error))
            return
        if provider is None:
            messagebox.showinfo("Provider not found", "Refresh the list and try again.")
            self.search()
            return

        labels = ["Name", "Service", "Location", "Phone", "Price (optional)", "Notes (optional)", "Latitude (optional)", "Longitude (optional)", "Opening hours (optional)", "Website (optional)"]
        initial = [provider["name"], provider["service"], provider["location"], provider["phone"], provider["price"] or "", provider["notes"] or "", provider["latitude"] or "", provider["longitude"] or "", provider["opening_hours"] or "", provider["website"] or ""]
        self._form_dialog("Edit provider", labels, lambda values, window: self._update_provider(provider_id, values, window), initial)

    def _update_provider(self, provider_id, values, window):
        name, service, location, phone, price, notes, latitude, longitude, opening_hours, website = values
        if not self.validate_provider(name, service, location, phone, latitude, longitude, window, exclude_id=provider_id):
            return
        latitude, longitude = self.parse_coordinates(latitude, longitude, window)
        if latitude is False:
            return
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute(
                    "UPDATE providers SET name = %s, service = %s, location = %s, phone = %s, price = %s, notes = %s, latitude = %s, longitude = %s, opening_hours = %s, website = %s WHERE id = %s",
                    (name, service, location, phone, price, notes, latitude, longitude, opening_hours, website, provider_id),
                )
                db.commit()
                cursor.close()
            window.destroy()
            self.show_all()
            messagebox.showinfo("Provider updated", f"{name} was updated.", parent=self)
        except Exception as error:
            messagebox.showerror("Could not update provider", str(error), parent=window)

    def validate_provider(self, name, service, location, phone, latitude, longitude, parent, exclude_id=None):
        if not all((name, service, location, phone)):
            messagebox.showwarning("Missing information", "Name, service, location, and phone are required.", parent=parent)
            return False
        digit_count = sum(character.isdigit() for character in phone)
        if not 7 <= digit_count <= 15:
            messagebox.showwarning("Check phone number", "Enter a phone number with 7 to 15 digits. Spaces, +, and hyphens are okay.", parent=parent)
            return False
        if bool(latitude) != bool(longitude):
            messagebox.showwarning("Incomplete coordinates", "Enter both latitude and longitude, or leave both blank.", parent=parent)
            return False
        if latitude:
            try:
                lat_value, lon_value = float(latitude), float(longitude)
                if not (-90 <= lat_value <= 90 and -180 <= lon_value <= 180):
                    raise ValueError
            except ValueError:
                messagebox.showwarning("Invalid coordinates", "Latitude must be from -90 to 90 and longitude from -180 to 180.", parent=parent)
                return False
        try:
            with connect() as db:
                cursor = db.cursor()
                if exclude_id is None:
                    cursor.execute(
                        "SELECT id FROM providers WHERE LOWER(name) = LOWER(%s) AND LOWER(service) = LOWER(%s) AND LOWER(location) = LOWER(%s) LIMIT 1",
                        (name, service, location),
                    )
                else:
                    cursor.execute(
                        "SELECT id FROM providers WHERE LOWER(name) = LOWER(%s) AND LOWER(service) = LOWER(%s) AND LOWER(location) = LOWER(%s) AND id <> %s LIMIT 1",
                        (name, service, location, exclude_id),
                    )
                duplicate = cursor.fetchone()
                cursor.close()
        except Exception as error:
            messagebox.showerror("Could not check provider", str(error), parent=parent)
            return False
        if duplicate:
            messagebox.showwarning(
                "Possible duplicate",
                "A provider with the same name, service, and location is already listed.",
                parent=parent,
            )
            return False
        return True

    @staticmethod
    def parse_coordinates(latitude, longitude, _parent):
        if not latitude:
            return None, None
        return float(latitude), float(longitude)

    def remove_provider(self):
        if not self.require_admin():
            return
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider in the list first.")
            return
        values = self.results.item(selected[0], "values")
        provider_id, provider_name = int(values[0]), values[1]
        confirmed = messagebox.askyesno(
            "Remove provider",
            f"Remove {provider_name} permanently? Its reviews will also be deleted.",
            icon="warning",
        )
        if not confirmed:
            return
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute("DELETE FROM providers WHERE id = %s", (provider_id,))
                db.commit()
                cursor.close()
            self.show_all()
            self.status.config(text=f"Removed {provider_name}")
        except Exception as error:
            messagebox.showerror("Could not remove provider", str(error))

    def toggle_verified(self):
        if not self.require_admin():
            return
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider card first.")
            return
        provider_id = int(self.results.item(selected[0], "values")[0])
        try:
            with connect() as db:
                cursor = db.cursor()
                cursor.execute("SELECT verified FROM providers WHERE id = %s", (provider_id,))
                row = cursor.fetchone()
                if row is None:
                    messagebox.showinfo("Provider not found", "Refresh the provider list and try again.")
                    return
                verified = 0 if row[0] else 1
                cursor.execute("UPDATE providers SET verified = %s WHERE id = %s", (verified, provider_id))
                db.commit()
                cursor.close()
            self.search()
            self.status.config(text="Provider verified" if verified else "Verification removed")
        except Exception as error:
            messagebox.showerror("Could not update verification", str(error))

    def view_details(self):
        selected = self.results.selection()
        if not selected:
            messagebox.showinfo("Select a provider", "Choose a provider in the list first.")
            return
        provider_id = int(self.results.item(selected[0], "values")[0])
        try:
            with connect() as db:
                cursor = db.cursor(dictionary=True)
                cursor.execute(
                    """SELECT p.*, COUNT(r.id) AS review_count, AVG(r.rating) AS average_rating
                       FROM providers p LEFT JOIN reviews r ON r.provider_id = p.id
                       WHERE p.id = %s GROUP BY p.id""",
                    (provider_id,),
                )
                provider = cursor.fetchone()
                cursor.execute(
                    "SELECT reviewer, rating, comment, created_at FROM reviews WHERE provider_id = %s ORDER BY created_at DESC",
                    (provider_id,),
                )
                reviews = cursor.fetchall()
                cursor.close()
        except Exception as error:
            messagebox.showerror("Could not load provider", str(error))
            return
        if provider is None:
            messagebox.showinfo("Provider not found", "Refresh the list and try again.")
            self.search()
            return

        window = tk.Toplevel(self)
        window.title(f"{provider['name']} — Provider details")
        window.geometry("560x480")
        window.transient(self)
        body = ttk.Frame(window, padding=14)
        body.pack(fill="both", expand=True)
        rating_text = (
            f"{provider['average_rating']:.1f}/5 ({provider['review_count']} reviews)"
            if provider["review_count"] else "No reviews yet"
        )
        summary = (
            f"{provider['name']}\n{provider['service']} in {provider['location']}\n"
            f"Status: {'Verified listing' if provider['verified'] else 'Not verified'}\n"
            f"Phone: {provider['phone']}\nRating: {rating_text}\n"
            f"Price: {provider['price'] or 'Not provided'}\n"
            f"Hours: {provider['opening_hours'] or 'Not provided'}\n"
            f"Website: {provider['website'] or 'Not provided'}\n"
            f"Notes: {provider['notes'] or 'No additional notes'}"
        )
        ttk.Label(body, text=summary, justify="left", font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 12))
        ttk.Label(body, text="Reviews", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        review_box = tk.Text(body, wrap="word", height=12, state="normal")
        review_box.pack(fill="both", expand=True, pady=(5, 0))
        if reviews:
            for review in reviews:
                review_box.insert("end", f"{review['reviewer']} — {review['rating']}/5\n")
                review_box.insert("end", f"{review['comment']}\n")
                review_box.insert("end", f"{review['created_at']}\n\n")
        else:
            review_box.insert("end", "No one has reviewed this provider yet.")
        review_box.configure(state="disabled")

    def _form_dialog(self, title, labels, submit, initial=None):
        window = tk.Toplevel(self)
        window.title(title)
        window.transient(self)
        window.grab_set()
        frame = ttk.Frame(window, padding=14)
        frame.pack(fill="both", expand=True)
        entries = []
        for index, label in enumerate(labels):
            ttk.Label(frame, text=label).grid(row=index, column=0, sticky="w", pady=3)
            entry = ttk.Entry(frame, width=36)
            if initial is not None:
                entry.insert(0, initial[index])
            entry.grid(row=index, column=1, sticky="ew", pady=3)
            entries.append(entry)
            if label == "Latitude (optional)":
                RoundButton(frame, "Pick on map", lambda: self.open_map_picker(entries[2].get().strip(), entries[6], entries[7], window)).grid(row=index, column=2, padx=(8, 0))
        frame.columnconfigure(1, weight=1)
        RoundButton(frame, "Save provider", lambda: submit([entry.get().strip() for entry in entries], window), primary=True).grid(
            row=len(labels), column=1, sticky="e", pady=(8, 0)
        )
        entries[0].focus_set()

    def open_map_picker(self, address, latitude_entry, longitude_entry, parent):
        if tkintermapview is None:
            messagebox.showinfo("Map picker not installed", "In PowerShell, run: python -m pip install -r requirements.txt", parent=parent)
            return
        if not address:
            messagebox.showwarning("Enter a location", "Enter the provider's area or address in the Location field first.", parent=parent)
            return
        window = tk.Toplevel(parent)
        window.title("Choose provider location on map")
        window.geometry("820x620")
        window.transient(parent)
        window.grab_set()
        panel = ttk.Frame(window, padding=12)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="Search the provider's address, then click the exact spot on the map.", font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 8))
        search_row = ttk.Frame(panel)
        search_row.pack(fill="x", pady=(0, 8))
        address_entry = ttk.Entry(search_row)
        address_entry.insert(0, address)
        address_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))
        map_widget = tkintermapview.TkinterMapView(panel, width=780, height=440, corner_radius=8)
        map_widget.pack(fill="both", expand=True)
        coordinate_label = ttk.Label(panel, text="No point selected yet")
        coordinate_label.pack(anchor="w", pady=6)
        selected = {"coords": None, "marker": None}

        def choose_point(coords):
            selected["coords"] = (float(coords[0]), float(coords[1]))
            if selected["marker"]:
                selected["marker"].delete()
            selected["marker"] = map_widget.set_marker(*selected["coords"], text="Provider")
            coordinate_label.config(text=f"Selected map point: {selected['coords'][0]:.7f}, {selected['coords'][1]:.7f}")

        def find_address():
            query = address_entry.get().strip()
            if not query:
                return
            try:
                marker = map_widget.set_address(query, marker=True)
                if marker:
                    map_widget.set_zoom(17)
                    coordinate_label.config(text="Search result shown. Click the provider's exact spot on the map.")
            except Exception as error:
                messagebox.showerror("Address not found", f"Search for the address again or move the map and click the provider's exact location.\n\n{error}", parent=window)

        map_widget.add_left_click_map_command(choose_point)
        RoundButton(search_row, "Find address", find_address, primary=True).pack(side="right")
        find_address()

        def save_point():
            if not selected["coords"]:
                messagebox.showinfo("Choose a point", "Click the provider's exact location on the map first.", parent=window)
                return
            latitude_entry.delete(0, "end")
            latitude_entry.insert(0, f"{selected['coords'][0]:.7f}")
            longitude_entry.delete(0, "end")
            longitude_entry.insert(0, f"{selected['coords'][1]:.7f}")
            window.destroy()

        RoundButton(panel, "Use selected point", save_point, primary=True).pack(anchor="e", pady=(4, 0))


if __name__ == "__main__":
    ServiceFinderApp().mainloop()
