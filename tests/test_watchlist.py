"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service. Mirrors the fixture and assertion structure of
tests/test_collection.py.
"""

import pytest
from app import create_app, db
from models import User, Film
from services.watchlist_service import add_to_watchlist, get_watchlist
from services.collection_service import FilmNotFoundError


@pytest.fixture
def app():
    """Create an isolated test app with an in-memory database."""
    app = create_app(config={
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def sample_user(app):
    """A user to use in tests."""
    with app.app_context():
        user = User(username="testuser", email="test@example.com")
        db.session.add(user)
        db.session.commit()
        return user.id


@pytest.fixture
def sample_film(app):
    """A film to use in tests."""
    with app.app_context():
        film = Film(title="Paddington 2", year=2017, genre="Comedy")
        db.session.add(film)
        db.session.commit()
        return film.id


# ── Nonexistent film (Comment 3) ─────────────────────────────────────────────

def test_add_to_watchlist_nonexistent_film_raises(app, sample_user):
    """
    Adding a film_id that doesn't exist in the database should raise
    FilmNotFoundError, not a database integrity error.
    """
    with app.app_context():
        fake_film_id = "00000000-0000-0000-0000-000000000000"

        with pytest.raises(FilmNotFoundError):
            add_to_watchlist(user_id=sample_user, film_id=fake_film_id)


# ── get_watchlist sort order (Comment 5) ─────────────────────────────────────

def test_get_watchlist_defaults_to_date_added_newest_first(app, sample_user):
    """
    get_watchlist() should default to date-added order (newest first),
    consistent with get_collection().
    """
    with app.app_context():
        from datetime import datetime, timezone, timedelta

        film_a = Film(title="Alien", year=1979, genre="Horror")
        film_b = Film(title="Blade Runner", year=1982, genre="Sci-Fi")
        db.session.add_all([film_a, film_b])
        db.session.commit()

        earlier = datetime.now(timezone.utc) - timedelta(days=5)
        later = datetime.now(timezone.utc)

        from models import WatchlistEntry
        db.session.add_all([
            WatchlistEntry(user_id=sample_user, film_id=film_a.id, date_added=earlier),
            WatchlistEntry(user_id=sample_user, film_id=film_b.id, date_added=later),
        ])
        db.session.commit()

        titles = [f["title"] for f in get_watchlist(sample_user)]
        # Blade Runner was added later, so it comes first by default.
        assert titles == ["Blade Runner", "Alien"]


def test_get_watchlist_sort_by_title(app, sample_user):
    """
    get_watchlist(sort="title") should sort alphabetically by film title,
    regardless of when each entry was added.
    """
    with app.app_context():
        from datetime import datetime, timezone, timedelta

        film_a = Film(title="Alien", year=1979)
        film_b = Film(title="Blade Runner", year=1982)
        db.session.add_all([film_a, film_b])
        db.session.commit()

        from models import WatchlistEntry
        # Add Blade Runner later than Alien so date order != alphabetical order.
        db.session.add_all([
            WatchlistEntry(user_id=sample_user, film_id=film_a.id,
                           date_added=datetime.now(timezone.utc) - timedelta(days=1)),
            WatchlistEntry(user_id=sample_user, film_id=film_b.id,
                           date_added=datetime.now(timezone.utc)),
        ])
        db.session.commit()

        titles = [f["title"] for f in get_watchlist(sample_user, sort="title")]
        assert titles == ["Alien", "Blade Runner"]
