"""
services/watchlist_service.py — CineLog (feature/watchlist branch)

Business logic for the watchlist feature.
"""

from app import db
from models import Film, WatchlistEntry
from services.collection_service import FilmNotFoundError


class AlreadyInWatchlistError(Exception):
    """Raised when a film is already on the user's watchlist."""
    pass


class NotInWatchlistError(Exception):
    """Raised when trying to remove a film that isn't on the watchlist."""
    pass


def add_to_watchlist(user_id, film_id):
    """
    Add a film to a user's watchlist.

    Args:
        user_id (str): UUID of the user.
        film_id (str): UUID of the film.

    Returns:
        WatchlistEntry: The newly created entry.

    Raises:
        FilmNotFoundError: If film_id does not exist.
        AlreadyInWatchlistError: If the film is already on the user's watchlist.
    """
    film = db.session.get(Film, film_id)
    if film is None:
        raise FilmNotFoundError(f"No film found with id '{film_id}'")

    existing = WatchlistEntry.query.filter_by(
        user_id=user_id, film_id=film_id
    ).first()
    if existing:
        raise AlreadyInWatchlistError(
            f"Film '{film_id}' is already on this user's watchlist"
        )

    entry = WatchlistEntry(user_id=user_id, film_id=film_id)
    db.session.add(entry)
    db.session.commit()
    return entry


def remove_from_watchlist(user_id, film_id):
    """
    Remove a film from a user's watchlist.

    Args:
        user_id (str): UUID of the user.
        film_id (str): UUID of the film.

    Returns:
        bool: True if the entry was removed.

    Raises:
        NotInWatchlistError: If the film is not on the user's watchlist.
    """
    entry = WatchlistEntry.query.filter_by(
        user_id=user_id, film_id=film_id
    ).first()
    if entry is None:
        raise NotInWatchlistError(
            f"Film '{film_id}' is not on this user's watchlist"
        )

    db.session.delete(entry)
    db.session.commit()
    return True


def get_watchlist(user_id, sort="recent"):
    """
    Return all films on a user's watchlist.

    Args:
        user_id (str): UUID of the user.
        sort (str): Ordering of the results.
            "recent" (default) — by date added, newest first (matches
                                 get_collection and the reviewer's preference).
            "title"            — alphabetically by film title.

    Returns:
        list[dict]: List of film dicts with watchlist metadata attached.
    """
    query = WatchlistEntry.query.filter_by(user_id=user_id)
    if sort == "title":
        query = query.join(Film).order_by(Film.title.asc())
    else:  # "recent" — default
        query = query.order_by(WatchlistEntry.date_added.desc())
    entries = query.all()

    result = []
    for entry in entries:
        film = db.session.get(Film, entry.film_id)
        film_dict = film.to_dict()
        film_dict["date_added"] = entry.date_added.isoformat()
        film_dict["public"] = entry.public
        result.append(film_dict)

    return result
