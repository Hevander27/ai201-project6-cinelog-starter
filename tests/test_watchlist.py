"""
tests/test_watchlist.py — CineLog

Tests for the watchlist service. Mirrors the fixture and assertion structure of
tests/test_collection.py.
"""

import pytest
from app import create_app, db
from models import User, Film, WatchlistEntry
from services.watchlist_service import (
    add_to_watchlist,
    remove_from_watchlist,
    get_watchlist,
    AlreadyInWatchlistError,
    NotInWatchlistError,
)
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


# ── Deduplication (stretch: a test the review didn't ask for) ────────────────

def test_add_to_watchlist_duplicate_raises(app, sample_user, sample_film):
    """
    Adding the same film twice should raise AlreadyInWatchlistError and leave
    exactly one entry — the review asked for the dedup *fix* but never for a
    test locking the behavior in.
    """
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        with pytest.raises(AlreadyInWatchlistError):
            add_to_watchlist(user_id=sample_user, film_id=sample_film)

        count = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).count()
        assert count == 1


# ── User isolation (stretch: a second unrequested edge case) ─────────────────

def test_get_watchlist_only_returns_requested_users_entries(app, sample_user, sample_film):
    """
    One user's watchlist must never include another user's entries. Watchlists
    default to public, so a filtering bug here would leak across accounts.
    """
    with app.app_context():
        other = User(username="other", email="other@example.com")
        db.session.add(other)
        db.session.commit()

        add_to_watchlist(user_id=sample_user, film_id=sample_film)
        add_to_watchlist(user_id=other.id, film_id=sample_film)

        assert len(get_watchlist(sample_user)) == 1
        assert len(get_watchlist(other.id)) == 1


# ── Visibility toggle (stretch) ──────────────────────────────────────────────

def test_add_to_watchlist_defaults_to_public(app, sample_user, sample_film):
    """Entries are public by default (the documented Comment 4 decision)."""
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film)
        assert entry.public is True


def test_add_to_watchlist_respects_explicit_public_false(app, sample_user, sample_film):
    """A caller can opt out of the public default explicitly."""
    with app.app_context():
        entry = add_to_watchlist(user_id=sample_user, film_id=sample_film, public=False)
        assert entry.public is False


# ── Removal (stretch: remove_from_watchlist) ─────────────────────────────────

def test_remove_from_watchlist_removes_entry(app, sample_user, sample_film):
    """Removing a film on the watchlist deletes the entry and returns True."""
    with app.app_context():
        add_to_watchlist(user_id=sample_user, film_id=sample_film)

        assert remove_from_watchlist(user_id=sample_user, film_id=sample_film) is True

        remaining = WatchlistEntry.query.filter_by(
            user_id=sample_user, film_id=sample_film
        ).first()
        assert remaining is None


def test_remove_from_watchlist_not_present_raises(app, sample_user, sample_film):
    """
    Removing a film that isn't on the watchlist should raise NotInWatchlistError,
    mirroring remove_from_collection's NotInCollectionError behavior.
    """
    with app.app_context():
        with pytest.raises(NotInWatchlistError):
            remove_from_watchlist(user_id=sample_user, film_id=sample_film)
